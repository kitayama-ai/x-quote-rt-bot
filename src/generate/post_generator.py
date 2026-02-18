"""
X Auto Post System — Gemini連携 投稿生成

マスターデータ + プロンプトテンプレートを読み込み、1日3投稿を生成。
"""
import json
import re
import random
from datetime import datetime, date
from pathlib import Path

from google import genai

from src.config import Config
from src.analyze.scorer import PostScorer
from src.post.safety_checker import SafetyChecker


# 投稿タイプのローテーション（DESIGN.md §2-2）
WEEKLY_SCHEDULE = {
    0: {"morning": "問題提起", "noon": "How to",       "evening": "ストーリー"},    # 月
    1: {"morning": "反常識",   "noon": "リスト",        "evening": "気づき"},        # 火
    2: {"morning": "問題提起", "noon": "How to（保存狙い）", "evening": "失敗談"},    # 水
    3: {"morning": "権威引用", "noon": "リスト（保存狙い）", "evening": "振り返り"},  # 木
    4: {"morning": "反常識",   "noon": "How to",        "evening": "今週のまとめ"},  # 金
    5: {"morning": "ストーリー", "noon": "ツール紹介",   "evening": "自由枠"},        # 土
    6: {"morning": "モチベーション", "noon": "来週の予告", "evening": "コミュニティ系"}, # 日
}


class PostGenerator:
    """Gemini APIで投稿を生成"""

    def __init__(self, config: Config):
        self.config = config
        self.scorer = PostScorer()
        self.safety_checker = SafetyChecker(config.safety_rules)

        # Gemini初期化
        if config.gemini_api_key:
            self.client = genai.Client(api_key=config.gemini_api_key)
            self.model_name = config.gemini_model
        else:
            self.client = None
            self.model_name = None
            print("⚠️ GEMINI_API_KEY未設定。投稿生成はスキップされます。")

    def generate_daily_posts(
        self,
        target_date: date | None = None,
        past_posts: list[str] | None = None
    ) -> list[dict]:
        """
        1日分の投稿案を生成（3本）

        Returns:
            [{"text", "type", "time", "score", "safety"}]
        """
        target_date = target_date or date.today()
        weekday = target_date.weekday()
        schedule = WEEKLY_SCHEDULE.get(weekday, WEEKLY_SCHEDULE[0])

        master_data = self.config.load_master_data()
        prompt_template = self.config.load_prompt_template()

        slots = [
            ("morning", schedule["morning"]),
            ("noon", schedule["noon"]),
            ("evening", schedule["evening"]),
        ]

        results = []
        generated_texts = list(past_posts or [])

        for slot_name, post_type in slots:
            # 投稿時間を計算（±15分ランダム）
            slot_config = self.config.schedule[slot_name]
            jitter = random.randint(-slot_config["jitter_minutes"], slot_config["jitter_minutes"])
            hour = slot_config["base_hour"]
            minute = slot_config["base_minute"] + jitter
            if minute < 0:
                hour -= 1
                minute += 60
            elif minute >= 60:
                hour += 1
                minute -= 60
            time_str = f"{hour:02d}:{minute:02d}"

            # 投稿を生成
            text = self._generate_single(
                master_data=master_data,
                prompt_template=prompt_template,
                post_type=post_type,
                slot_name=slot_name,
                target_date=target_date
            )

            if not text:
                continue

            # スコアリング
            score = self.scorer.score(text, post_type)

            # 安全チェック
            safety = self.safety_checker.check(text, past_posts=generated_texts)

            # スコア低すぎ or 安全チェック不合格 → リトライ（最大2回）
            for retry in range(2):
                if score.total >= 6 and safety.is_safe:
                    break

                text = self._generate_single(
                    master_data=master_data,
                    prompt_template=prompt_template,
                    post_type=post_type,
                    slot_name=slot_name,
                    target_date=target_date,
                    retry_hint=self._build_retry_hint(score, safety)
                )
                if text:
                    score = self.scorer.score(text, post_type)
                    safety = self.safety_checker.check(text, past_posts=generated_texts)

            generated_texts.append(text)

            results.append({
                "text": text,
                "type": post_type,
                "time": time_str,
                "slot": slot_name,
                "score": score,
                "safety": safety,
                "date": target_date.isoformat(),
                "account_id": self.config.account_id
            })

        return results

    def _generate_single(
        self,
        master_data: str,
        prompt_template: str,
        post_type: str,
        slot_name: str,
        target_date: date,
        retry_hint: str = ""
    ) -> str | None:
        """Gemini APIで1投稿を生成"""
        if not self.client:
            return self._generate_demo(post_type, slot_name)

        weekday_ja = ["月", "火", "水", "木", "金", "土", "日"][target_date.weekday()]

        prompt = f"""
{prompt_template}

━━━━━━━━━━━━━━━━━━
■ 今回の条件
━━━━━━━━━━━━━━━━━━
- 日付: {target_date.isoformat()} ({weekday_ja}曜日)
- 投稿タイプ: {post_type}
- 時間帯: {slot_name} ({"朝" if slot_name == "morning" else "昼" if slot_name == "noon" else "夜"})
{"- リトライ指示: " + retry_hint if retry_hint else ""}

━━━━━━━━━━━━━━━━━━
■ マスターデータ（レンの人格・文体・ターゲット）
━━━━━━━━━━━━━━━━━━
{master_data[:3000]}

━━━━━━━━━━━━━━━━━━
■ 出力
━━━━━━━━━━━━━━━━━━
ツイート本文だけを出力しろ。余計な説明は一切不要。
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
            return text

        try:
            return retry_with_backoff(_call_gemini, max_retries=3, label="Gemini生成 ")
        except Exception as e:
            print(f"[Generator] Gemini APIエラー（リトライ全失敗）: {e}")
            return None

    def _generate_demo(self, post_type: str, slot_name: str) -> str:
        """デモ用のダミー投稿を返す"""
        demos = {
            "問題提起": (
                "ぶっちゃけ、AIに投稿を任せて\n"
                "AI感丸出しになってる人多すぎる。\n\n"
                "「素晴らしい」「革新的」「いかがでしたか」\n\n"
                "これ全部NGワード。\n\n"
                "僕はマスターデータっていう仕組みで\n"
                "AI感を完全に消してる。\n\n"
                "結果、3時間の作業が30分になった。\n\n"
                "やり方知りたい人いる？"
            ),
            "How to": (
                "GASで投稿を自動化する手順、\n"
                "全部公開する。\n\n"
                "①スプシにマスターデータを作る\n"
                "②GASでGemini APIを叩く\n"
                "③生成された投稿をXに自動投稿\n\n"
                "これだけ。\n\n"
                "コピペで動くコード付き。\n"
                "noteに全部書いた。\n\n"
                "→ プロフのリンクから"
            ),
            "ストーリー": (
                "正直、半年前は副業に\n"
                "1日3時間かけてた。\n\n"
                "投稿作成、分析、改善…\n"
                "全部手動。\n\n"
                "でもAI×GASで仕組み化したら\n"
                "30分で全部終わるようになった。\n\n"
                "空いた時間で新しい仕組みを\n"
                "作ってる。\n\n"
                "これが複利。マジで。"
            ),
        }
        # マッチするものが無ければランダムに返す
        for key in demos:
            if key in post_type:
                return demos[key]
        return random.choice(list(demos.values()))

    def _build_retry_hint(self, score, safety) -> str:
        """リトライ時のヒントを構築"""
        hints = []
        if score.total < 6:
            if score.hook < 2:
                hints.append("フックをもっと強くしろ（数字・感情・断定を使え）")
            if score.specificity < 2:
                hints.append("具体的な数字やツール名を入れろ")
            if score.humanity < 2:
                hints.append("もっとカジュアルに。「マジで」「ぶっちゃけ」等を使え")
        if not safety.is_safe:
            hints.append(f"以下を修正: {', '.join(safety.violations)}")
        return '; '.join(hints)


def save_daily_output(posts: list[dict], output_dir: Path | None = None):
    """日次生成結果をJSONファイルに保存"""
    from src.config import PROJECT_ROOT
    output_dir = output_dir or PROJECT_ROOT / "data" / "output" / "daily"
    output_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    account_id = posts[0]["account_id"] if posts else "unknown"

    # ScoreResult/SafetyResultをシリアライズ
    serializable = []
    for p in posts:
        item = {k: v for k, v in p.items() if k not in ("score", "safety")}
        if p.get("score"):
            item["score"] = {
                "total": p["score"].total,
                "rank": p["score"].rank,
                "hook": p["score"].hook,
                "specificity": p["score"].specificity,
                "humanity": p["score"].humanity,
                "structure": p["score"].structure,
                "cta": p["score"].cta,
                "details": p["score"].details
            }
        if p.get("safety"):
            item["safety"] = {
                "is_safe": p["safety"].is_safe,
                "violations": p["safety"].violations,
                "warnings": p["safety"].warnings
            }
        serializable.append(item)

    filepath = output_dir / f"{today}_{account_id}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)

    print(f"📁 保存: {filepath}")
    return filepath
