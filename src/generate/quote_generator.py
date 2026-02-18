"""
X Auto Post System — 引用RT投稿文生成

海外AIバズツイートを翻訳・要約し、レンの口調で引用RTコメントを生成する。
5パターンのテンプレートをローテーションして多様性を確保。
"""
import json
import re
import random
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

from google import genai

from src.config import Config, PROJECT_ROOT
from src.analyze.scorer import PostScorer
from src.post.safety_checker import SafetyChecker

JST = ZoneInfo("Asia/Tokyo")

# テンプレートID
TEMPLATE_IDS = [
    "translate_comment",  # 翻訳+自分コメント型
    "summary_points",     # 要点まとめ型
    "question_prompt",    # 問題提起型
    "practice_report",    # 実践レポート型
    "breaking_news",      # 速報型
]


class QuoteGenerator:
    """引用RT投稿文を生成"""

    def __init__(self, config: Config):
        self.config = config
        self.scorer = PostScorer()
        self.safety_checker = SafetyChecker(config.safety_rules)

        # 引用RTルール読み込み
        rules_path = PROJECT_ROOT / "config" / "quote_rt_rules.json"
        with open(rules_path, "r", encoding="utf-8") as f:
            self.quote_rules = json.load(f)

        # プロンプトテンプレート読み込み
        template_path = PROJECT_ROOT / "src" / "generate" / "templates" / "quote_rt_template.md"
        with open(template_path, "r", encoding="utf-8") as f:
            self.prompt_template = f.read()

        # Gemini初期化
        if config.gemini_api_key:
            self.client = genai.Client(api_key=config.gemini_api_key)
            self.model_name = config.gemini_model
        else:
            self.client = None
            self.model_name = None
            print("⚠️ GEMINI_API_KEY未設定。引用RT生成はデモモードで動作します。")

        # テンプレート使用回数トラッキング（日次リセット）
        self._template_usage: dict[str, int] = {}
        self._usage_date: str = ""

    def _get_template_id(self, preferred: str = "") -> str:
        """
        テンプレートIDを選択（使用回数制限あり）

        Args:
            preferred: 指定テンプレートID（省略時はローテーション）
        """
        today = date.today().isoformat()
        if self._usage_date != today:
            self._template_usage = {}
            self._usage_date = today

        templates = self.quote_rules.get("templates", [])
        max_daily = {t["id"]: t.get("max_daily_uses", 2) for t in templates}

        # 指定テンプレートが使用可能ならそれを返す
        if preferred and preferred in max_daily:
            if self._template_usage.get(preferred, 0) < max_daily[preferred]:
                return preferred

        # 使用可能なテンプレートからランダム選択
        available = [
            tid for tid in TEMPLATE_IDS
            if self._template_usage.get(tid, 0) < max_daily.get(tid, 2)
        ]

        if not available:
            # 全テンプレート上限到達 → リセットして再選択
            available = TEMPLATE_IDS

        return random.choice(available)

    def generate(
        self,
        original_text: str,
        author_username: str = "",
        author_name: str = "",
        likes: int = 0,
        retweets: int = 0,
        template_id: str = "",
        past_posts: list[str] | None = None,
    ) -> dict:
        """
        引用RT投稿文を生成

        Args:
            original_text: 元ツイートのテキスト（英語）
            author_username: 元ツイートの著者ユーザー名
            author_name: 元ツイートの著者表示名
            likes: いいね数
            retweets: RT数
            template_id: 使用テンプレートID（省略時は自動選択）
            past_posts: 過去の投稿テキスト（重複チェック用）

        Returns:
            {"text", "template_id", "score", "safety", "original_text", ...}
        """
        template_id = self._get_template_id(template_id)

        text = self._generate_single(
            original_text=original_text,
            author_username=author_username,
            author_name=author_name,
            likes=likes,
            retweets=retweets,
            template_id=template_id,
        )

        if not text:
            return {"text": "", "template_id": template_id, "error": "生成失敗"}

        # スコアリング & 安全チェック
        score = self.scorer.score(text, post_type="引用RT")
        safety = self.safety_checker.check(text, past_posts=past_posts or [])

        # リトライ（スコア低い or 安全チェック不合格）
        for retry in range(2):
            if score.total >= 5 and safety.is_safe:
                break

            retry_hint = self._build_retry_hint(score, safety)
            text = self._generate_single(
                original_text=original_text,
                author_username=author_username,
                author_name=author_name,
                likes=likes,
                retweets=retweets,
                template_id=template_id,
                retry_hint=retry_hint,
            )
            if text:
                score = self.scorer.score(text, post_type="引用RT")
                safety = self.safety_checker.check(text, past_posts=past_posts or [])

        # テンプレート使用回数を更新
        self._template_usage[template_id] = self._template_usage.get(template_id, 0) + 1

        return {
            "text": text or "",
            "template_id": template_id,
            "score": score,
            "safety": safety,
            "original_text": original_text,
            "author_username": author_username,
            "author_name": author_name,
            "likes": likes,
            "retweets": retweets,
        }

    def generate_batch(
        self,
        tweets: list[dict],
        max_count: int = 10,
        past_posts: list[str] | None = None,
    ) -> list[dict]:
        """
        複数ツイートの引用RT文を一括生成

        Args:
            tweets: [{"text", "author_username", "likes", ...}]
            max_count: 最大生成数
            past_posts: 重複チェック用

        Returns:
            [{"text", "template_id", "score", ...}]
        """
        results = []
        generated_texts = list(past_posts or [])

        for tweet in tweets[:max_count]:
            result = self.generate(
                original_text=tweet.get("text", ""),
                author_username=tweet.get("author_username", ""),
                author_name=tweet.get("author_name", ""),
                likes=tweet.get("likes", 0),
                retweets=tweet.get("retweets", 0),
                past_posts=generated_texts,
            )

            if result.get("text"):
                generated_texts.append(result["text"])
                results.append(result)

        return results

    def _generate_single(
        self,
        original_text: str,
        author_username: str,
        author_name: str,
        likes: int,
        retweets: int,
        template_id: str,
        retry_hint: str = "",
    ) -> str | None:
        """Gemini APIで引用RTコメントを1件生成"""
        if not self.client:
            return self._generate_demo(original_text, template_id)

        # テンプレート情報
        template_info = ""
        for t in self.quote_rules.get("templates", []):
            if t["id"] == template_id:
                template_info = f"テンプレート: {t['name']} — {t['description']}"
                break

        prompt = f"""
{self.prompt_template}

━━━━━━━━━━━━━━━━━━
■ 今回の条件
━━━━━━━━━━━━━━━━━━
- {template_info}
- テンプレートID: {template_id}
{"- リトライ指示: " + retry_hint if retry_hint else ""}

━━━━━━━━━━━━━━━━━━
■ 元ツイート情報
━━━━━━━━━━━━━━━━━━
- 著者: @{author_username} ({author_name})
- いいね: {likes:,}件 / RT: {retweets:,}件
- テキスト（英語原文）:
{original_text}

━━━━━━━━━━━━━━━━━━
■ 出力
━━━━━━━━━━━━━━━━━━
ツイート本文だけを出力しろ。余計な説明は一切不要。250字以内。
"""

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            text = response.text.strip()
            # コードブロックや引用符を除去
            text = re.sub(r'^```.*?\n', '', text)
            text = re.sub(r'\n```$', '', text)
            text = text.strip('"\'`')
            return text
        except Exception as e:
            print(f"[QuoteGenerator] Gemini APIエラー: {e}")
            return None

    def _generate_demo(self, original_text: str, template_id: str) -> str:
        """デモ用のダミー引用RTを返す"""
        demos = {
            "translate_comment": (
                "海外で今めちゃくちゃ話題になってるAIの使い方。\n\n"
                "僕的なポイントは\n"
                "「自動化の範囲が想像以上に広い」ってこと。\n\n"
                "日本だとまだ手動でやってる人多いけど\n"
                "これ知ったら世界変わる。\n\n"
                "早めに触っておくべき。"
            ),
            "summary_points": (
                "海外で今バズってるAIの新しい使い方。\n"
                "ポイントは3つ:\n\n"
                "・従来の10倍速で処理できる\n"
                "・コード書けなくてもOK\n"
                "・無料で始められる\n\n"
                "ガチでこれは来る。"
            ),
            "question_prompt": (
                "AIエージェントが自分で判断して動く時代、\n"
                "マジで来てる。\n\n"
                "これ日本でも半年以内に\n"
                "当たり前になる。\n\n"
                "準備してない人は置いていかれる。"
            ),
            "practice_report": (
                "海外で話題のAI自動化手法。\n\n"
                "実際に試してみた。\n"
                "結果: 3時間の作業が20分になった。\n\n"
                "しかもミスゼロ。\n"
                "これはガチで使える。"
            ),
            "breaking_news": (
                "これはデカい。\n\n"
                "AIの使い方が根本から変わる可能性。\n\n"
                "今までの常識が通用しなくなる。\n"
                "早めに触っておいた方がいい。"
            ),
        }
        return demos.get(template_id, demos["translate_comment"])

    def _build_retry_hint(self, score, safety) -> str:
        """リトライ時のヒント"""
        hints = []
        if score.total < 5:
            if score.hook < 2:
                hints.append("フックを強くしろ")
            if score.humanity < 2:
                hints.append("もっとカジュアルに")
        if not safety.is_safe:
            hints.append(f"修正: {', '.join(safety.violations)}")

        # 引用RT固有のチェック
        rules = self.quote_rules.get("quote_rt", {})
        min_len = rules.get("min_comment_length", 30)
        hints.append(f"最低{min_len}字以上のコメントを書け")

        return '; '.join(hints)
