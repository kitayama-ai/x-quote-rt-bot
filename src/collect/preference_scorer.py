"""
X Auto Post System — プリファレンスベースのツイートスコアリング

クライアントの選定プリファレンス（トピック、キーワード、アカウント優先度）に基づいて
収集ツイートにマッチスコアを付与する。LLM不要の高速キーワードクラスタ方式。
"""
import json
import re
from pathlib import Path

from src.config import PROJECT_ROOT

# デフォルトのプリファレンスファイルパス
PREFERENCES_PATH = PROJECT_ROOT / "config" / "selection_preferences.json"


class PreferenceScorer:
    """クライアントプリファレンスに基づくツイートスコアリング"""

    def __init__(self, preferences_path: Path | None = None):
        self._path = preferences_path or PREFERENCES_PATH
        self._load_preferences()

    def _load_preferences(self):
        """プリファレンス設定を読み込み"""
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._prefs = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._prefs = {}

        self._weekly_focus = self._prefs.get("weekly_focus", {})
        self._topic_prefs = self._prefs.get("topic_preferences", {})
        self._account_overrides = self._prefs.get("account_overrides", {})
        self._keyword_weights = self._prefs.get("keyword_weights", {})
        self._topic_clusters = self._prefs.get("topic_clusters", {})
        self._threshold_overrides = self._prefs.get("threshold_overrides", {})

    def reload(self):
        """設定を再読み込み"""
        self._load_preferences()

    def score(self, tweet_text: str, author_username: str = "") -> dict:
        """
        ツイートをプリファレンスに基づいてスコアリング

        Args:
            tweet_text: ツイート本文（英語）
            author_username: ツイート著者のユーザー名

        Returns:
            {
                "preference_score": float,   # 0.0 ~ 5.0+
                "matched_topics": list[str],
                "matched_keywords": list[str],
                "is_blocked": bool,
                "is_focus_match": bool,
            }
        """
        text_lower = tweet_text.lower()

        # ブロックチェック
        blocked = self._account_overrides.get("blocked", [])
        if author_username.lower() in [b.lower() for b in blocked]:
            return {
                "preference_score": 0.0,
                "matched_topics": [],
                "matched_keywords": [],
                "is_blocked": True,
                "is_focus_match": False,
            }

        score = 1.0  # ベーススコア

        # ── 1. キーワードマッチ ──
        matched_keywords = []
        keyword_score = 0.0
        for keyword, weight in self._keyword_weights.items():
            if keyword.lower() in text_lower:
                matched_keywords.append(keyword)
                keyword_score += weight

        # キーワードスコア（最大2.0に正規化）
        if keyword_score > 0:
            score += min(keyword_score, 2.0)

        # ── 2. トピック分類 ──
        matched_topics = self._classify_topics(text_lower)
        topic_score = 0.0

        preferred = [t.lower() for t in self._topic_prefs.get("preferred", [])]
        avoid = [t.lower() for t in self._topic_prefs.get("avoid", [])]

        for topic in matched_topics:
            if topic.lower() in preferred:
                topic_score += 1.0
            elif topic.lower() in avoid:
                topic_score -= 1.5  # 回避トピックは強めのペナルティ

        score += topic_score

        # ── 3. アカウントブースト ──
        boosted = self._account_overrides.get("boosted", [])
        if author_username.lower() in [b.lower() for b in boosted]:
            score *= 1.5

        # ── 4. 週次フォーカスボーナス ──
        is_focus_match = False
        focus_keywords = self._weekly_focus.get("focus_keywords", [])
        focus_accounts = self._weekly_focus.get("focus_accounts", [])

        for fk in focus_keywords:
            if fk.lower() in text_lower:
                is_focus_match = True
                score += 0.5
                break

        if author_username.lower() in [fa.lower() for fa in focus_accounts]:
            is_focus_match = True
            score += 0.5

        # スコア下限: 0.0
        score = max(score, 0.0)

        return {
            "preference_score": round(score, 2),
            "matched_topics": matched_topics,
            "matched_keywords": matched_keywords,
            "is_blocked": False,
            "is_focus_match": is_focus_match,
        }

    def _classify_topics(self, text_lower: str) -> list[str]:
        """
        テキストをトピッククラスタに基づいて分類

        Returns:
            マッチしたトピック名のリスト
        """
        matched = []
        for topic, keywords in self._topic_clusters.items():
            match_count = sum(
                1 for kw in keywords
                if kw.lower() in text_lower
            )
            # 2つ以上のキーワードがマッチ or 1つのキーワードが十分にユニーク（3文字以上）
            if match_count >= 2 or (match_count == 1 and any(
                len(kw) >= 5 and kw.lower() in text_lower for kw in keywords
            )):
                matched.append(topic)

        return matched

    def get_threshold_override(self, key: str) -> int | None:
        """
        閾値の上書き値を取得

        Args:
            key: "min_likes", "max_age_hours" etc.

        Returns:
            上書き値 or None（デフォルト使用）
        """
        val = self._threshold_overrides.get(key)
        if val is not None and val != "":
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
        return None

    def is_account_blocked(self, username: str) -> bool:
        """アカウントがブロックされているか"""
        blocked = self._account_overrides.get("blocked", [])
        return username.lower() in [b.lower() for b in blocked]

    @property
    def preferences(self) -> dict:
        """現在のプリファレンス設定を返す"""
        return self._prefs.copy()

    def format_score(self, result: dict) -> str:
        """スコア結果をフォーマット"""
        lines = [f"  プリファレンススコア: {result['preference_score']}"]
        if result["matched_topics"]:
            lines.append(f"  マッチトピック: {', '.join(result['matched_topics'])}")
        if result["matched_keywords"]:
            lines.append(f"  マッチキーワード: {', '.join(result['matched_keywords'])}")
        if result["is_focus_match"]:
            lines.append("  フォーカスマッチ!")
        if result["is_blocked"]:
            lines.append("  ブロック対象")
        return "\n".join(lines)
