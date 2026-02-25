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

# テンプレートID（8パターン）
TEMPLATE_IDS = [
    "translate_comment",  # 市場インパクト型
    "summary_points",     # 要点まとめ型
    "question_prompt",    # 警告・問題提起型
    "practice_report",    # 激震分析型
    "breaking_news",      # 衝撃速報型
    "exclusive_report",   # 独占入手型
    "dark_alert",         # ダーク警告型
    "legend_moment",      # 伝説・歴史型
]


class QuoteGenerator:
    """引用RT投稿文を生成"""

    def __init__(self, config: Config, persona_profile: dict | None = None):
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

        # ダッシュボードからのプロンプト上書き設定を読み込み
        self._prompt_overrides = self._load_prompt_overrides()
        if self._prompt_overrides:
            self.prompt_template = self._apply_prompt_overrides(self.prompt_template)

        # ペルソナプロファイル（文体コピー用）
        # Xアカウントの過去ツイートから分析した文体データ
        self._persona_profile = persona_profile
        if not self._persona_profile:
            self._persona_profile = config.load_persona_profile()
        self._persona_prompt = self._build_persona_prompt()

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
        # 直近使用テンプレート履歴（連続同一パターン防止）
        self._recent_templates: list[str] = []

    def _load_prompt_overrides(self) -> dict:
        """selection_preferences.json から prompt_overrides を読み込み"""
        prefs_path = PROJECT_ROOT / "config" / "selection_preferences.json"
        try:
            with open(prefs_path, "r", encoding="utf-8") as f:
                prefs = json.load(f)
            return prefs.get("prompt_overrides", {})
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _apply_prompt_overrides(self, template: str) -> str:
        """ダッシュボード設定でプロンプトテンプレートを動的に上書き"""
        po = self._prompt_overrides
        if not po:
            return template

        # ペルソナ名の置換
        name = po.get("persona_name", "").strip()
        if name and name != "レン":
            template = template.replace("「レン」", f"「{name}」")
            template = template.replace("レンの口調", f"{name}の口調")

        # 一人称の置換
        fp = po.get("first_person", "").strip()
        if fp and fp != "僕":
            template = template.replace("一人称:「僕」", f"一人称:「{fp}」")
            template = template.replace("僕的な", f"{fp}的な")

        # ポジションの置換
        pos = po.get("position", "").strip()
        if pos:
            template = re.sub(
                r"- \*\*ポジション\*\*: .+",
                f"- **ポジション**: {pos}",
                template,
            )

        # 差別化の置換
        diff = po.get("differentiator", "").strip()
        if diff:
            template = re.sub(
                r"- \*\*差別化\*\*: .+",
                f"- **差別化**: {diff}",
                template,
            )

        # トーンの置換
        tone = po.get("tone", "").strip()
        if tone:
            template = re.sub(
                r"- \*\*トーン\*\*: .+",
                f"- **トーン**: {tone}",
                template,
            )

        # 文体ルールの置換
        style = po.get("style_patterns", "").strip()
        if style:
            style_lines = "\n".join(f"- {line.strip()}" for line in style.split("\n") if line.strip())
            template = re.sub(
                r"(■ 文体ルール.+?━+\n\n)[\s\S]*?(━━━)",
                rf"\1{style_lines}\n\n\2",
                template,
            )

        # NGワードの追加
        ng = po.get("ng_words", "").strip()
        if ng:
            ng_list = [w.strip() for w in ng.split(",") if w.strip()]
            existing_section = template.find("■ 絶対NG")
            if existing_section != -1:
                # NGセクションの末尾に追加
                for word in ng_list:
                    if word not in template:
                        insert_pos = template.find("\n━", existing_section + 1)
                        if insert_pos != -1:
                            template = template[:insert_pos] + f"\n- 「{word}」" + template[insert_pos:]

        # カスタム指示の追加（出力セクションの前に挿入）
        custom = po.get("custom_directive", "").strip()
        if custom:
            insert_marker = "━━━━━━━━━━━━━━━━━━\n■ 出力"
            if insert_marker in template:
                custom_section = (
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"■ クライアント追加指示\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"{custom}\n\n"
                )
                template = template.replace(insert_marker, custom_section + insert_marker)

        return template

    def _build_persona_prompt(self) -> str:
        """ペルソナプロファイルからプロンプト注入テキストを生成"""
        if not self._persona_profile:
            return ""

        # PersonaProfile.to_prompt_injection() の出力を使う
        # または dict から直接構築
        try:
            from src.analyze.persona_analyzer import PersonaProfile
            if isinstance(self._persona_profile, dict):
                pp = PersonaProfile(**{
                    k: v for k, v in self._persona_profile.items()
                    if k in PersonaProfile.__dataclass_fields__
                })
                return pp.to_prompt_injection()
            elif isinstance(self._persona_profile, PersonaProfile):
                return self._persona_profile.to_prompt_injection()
        except Exception:
            pass

        return ""

    def _get_template_id(self, preferred: str = "") -> str:
        """
        テンプレートIDを選択（使用回数制限 + 連続使用防止）

        Args:
            preferred: 指定テンプレートID（省略時はローテーション）
        """
        today = date.today().isoformat()
        if self._usage_date != today:
            self._template_usage = {}
            self._recent_templates = []
            self._usage_date = today

        templates = self.quote_rules.get("templates", [])
        max_daily = {t["id"]: t.get("max_daily_uses", 2) for t in templates}

        # ダッシュボードで有効化されたテンプレートのみ使用
        enabled_csv = self._prompt_overrides.get("enabled_templates", "")
        if enabled_csv:
            enabled_ids = [t.strip() for t in enabled_csv.split(",") if t.strip()]
        else:
            enabled_ids = TEMPLATE_IDS  # デフォルト: 全テンプレート有効

        # 指定テンプレートが使用可能ならそれを返す
        if preferred and preferred in max_daily and preferred in enabled_ids:
            if self._template_usage.get(preferred, 0) < max_daily[preferred]:
                return preferred

        # 使用可能なテンプレートからランダム選択
        available = [
            tid for tid in enabled_ids
            if tid in TEMPLATE_IDS  # 有効なIDのみ
            and self._template_usage.get(tid, 0) < max_daily.get(tid, 2)
        ]

        if not available:
            # 全テンプレート上限到達 → リセットして再選択
            available = enabled_ids if enabled_ids else TEMPLATE_IDS

        # ── バリエーション強制: 直近2件と異なるテンプレートを優先 ──
        if len(available) > 1 and self._recent_templates:
            # 直近2件のテンプレートを除外した候補
            recent_set = set(self._recent_templates[-2:])
            non_recent = [tid for tid in available if tid not in recent_set]
            if non_recent:
                available = non_recent

        chosen = random.choice(available)

        # 履歴を更新（最大10件保持）
        self._recent_templates.append(chosen)
        if len(self._recent_templates) > 10:
            self._recent_templates = self._recent_templates[-10:]

        return chosen

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
            past_posts=past_posts,
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
                past_posts=past_posts,
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
        past_posts: list[str] | None = None,
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

        # ── バリエーション強制: 直近の生成物の冒頭を見せて被り回避 ──
        variety_hint = ""
        if past_posts:
            recent_openings = []
            for p in past_posts[-5:]:
                first_line = p.strip().split("\n")[0][:40] if p.strip() else ""
                if first_line:
                    recent_openings.append(first_line)
            if recent_openings:
                variety_hint = (
                    "━━━━━━━━━━━━━━━━━━\n"
                    "■ バリエーション指示（超重要）\n"
                    "━━━━━━━━━━━━━━━━━━\n\n"
                    "以下は直近の生成済み投稿の冒頭。これらと**同じ見出し語・同じ冒頭パターン**は絶対に使うな。\n"
                    "異なる表現・異なる切り口で書け。\n\n"
                    + "\n".join(f"- {o}" for o in recent_openings)
                    + "\n\n"
                )

        prompt = f"""
{self.prompt_template}

{self._persona_prompt if self._persona_prompt else ""}

{variety_hint}━━━━━━━━━━━━━━━━━━
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
ツイート本文だけを出力しろ。余計な説明は一切不要。必ず120字以内（X APIの日本語文字カウント制限）。
"""

        from src.utils import retry_with_backoff

        def _call_gemini():
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            text = response.text.strip()
            text = re.sub(r'^```.*?\n', '', text)
            text = re.sub(r'\n```$', '', text)
            text = text.strip('"\'`')
            # X API: 日本語は1文字=2カウント。quote_tweet_id分(23)含め280以内
            # 安全上限: 120文字（120×2+23=263カウント ≤ 280）
            if len(text) > 120:
                text = text[:117] + "..."
            return text

        try:
            return retry_with_backoff(_call_gemini, max_retries=3, label="QuoteRT生成 ")
        except Exception as e:
            print(f"[QuoteGenerator] Gemini APIエラー（リトライ全失敗）: {e}")
            return None

    def _generate_demo(self, original_text: str, template_id: str) -> str:
        """デモ用のダミー引用RTを返す"""
        demos = {
            "translate_comment": (
                "🚨【AI革命】GPT-5のマルチモーダル機能が全業界を変える。\n\n"
                "市場への影響は計り知れない。🏛️✨\n"
                "・AI関連銘柄の時価総額が「2兆ドル」を突破する勢い\n"
                "・従来のSaaS企業は淘汰の危機\n\n"
                "投資家は今すぐポートフォリオの見直しを。"
            ),
            "summary_points": (
                "💥【速報】OpenAI、企業向けAIエージェントを正式リリース。\n\n"
                "業界の構図が一変する3つのポイント。🏛️📈\n"
                "・自律型AIが「月額$200」で導入可能に\n"
                "・コード不要で業務自動化が完結\n"
                "・初月で10万社が導入申請\n\n"
                "SaaS業界、生き残りの分水嶺。"
            ),
            "question_prompt": (
                "🚨【警告】米国AI規制法案、来月にも議会通過の見通し。\n\n"
                "Web3・暗号資産にも波及する「実績」。🏛️🔥\n"
                "・AIモデルの学習データに開示義務\n"
                "・違反企業は最大「売上高10%」の罰金\n\n"
                "規制は止められない。備えろ。"
            ),
            "practice_report": (
                "💥【激震】Google DeepMind、AGI到達の内部メモが流出。\n\n"
                "AI業界の「地殻変動」が始まった。🏛️📊\n"
                "・2026年末までに汎用人工知能の実現を示唆\n"
                "・GoogleのAI投資額は年間「500億ドル」超\n\n"
                "もはや止まらない。歴史の転換点。"
            ),
            "breaking_news": (
                "🚨【衝撃】Apple、独自AIチップで「NVIDIA離れ」を宣言。\n\n"
                "半導体市場に激震が走る。🏛️🇺🇸\n"
                "・自社開発チップのAI推論性能がH100を「40%」上回る\n"
                "・NVIDIA株が時間外で8%急落\n\n"
                "AI覇権の構図が根本から変わる。"
            ),
            "exclusive_report": (
                "💥【独占】ソフトバンク孫正義、さらに「3兆円」のAI投資を決断。\n\n"
                "世界最大のAIファンドが動いた。🏛️💎\n"
                "・OpenAI、Anthropicに追加出資\n"
                "・日本国内にAIデータセンター10拠点建設\n"
                "・目指すは「AI大国ニッポン」の復権。"
            ),
            "dark_alert": (
                "💀米国失業率、AI自動化で「14.2%」に急騰の予測。\n\n"
                "ウォール街のAIリサーチが衝撃のデータを公開。🏛️🩸\n"
                "・ホワイトカラー職の38%が3年以内に消滅リスク\n"
                "・再就職までの平均期間は「18ヶ月」\n\n"
                "静かに、しかし確実に雇用崩壊は始まっている。"
            ),
            "legend_moment": (
                "💥【伝説】ビットコイン、ついに「$200,000」の大台を突破。\n\n"
                "暗号資産の歴史が書き換えられた。🏛️✨\n"
                "・時価総額は「4兆ドル」でAppleを超える\n"
                "・機関投資家の参入率が過去最高の67%\n\n"
                "もう誰もBTCを無視できない。新時代の幕開け。"
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
