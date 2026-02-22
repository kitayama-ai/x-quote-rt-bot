"""
X Auto Post System — 収集ツイートキュー管理

手動収集(パターンA)とAPI収集(パターンB)の両方で共通に使用。
キューへの追加・承認・削除・日次取得を管理する。
"""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.collect.tweet_parser import ParsedTweet
from src.config import PROJECT_ROOT

JST = ZoneInfo("Asia/Tokyo")

# キューファイルのパス
QUEUE_DIR = PROJECT_ROOT / "data" / "queue"
PENDING_FILE = QUEUE_DIR / "pending_tweets.json"
PROCESSED_FILE = QUEUE_DIR / "processed_tweets.json"
FEEDBACK_FILE = PROJECT_ROOT / "data" / "feedback" / "selection_feedback.json"

# スキップ理由の選択肢
SKIP_REASONS = [
    "topic_mismatch",     # トピック不一致
    "source_untrusted",   # ソース不適切
    "too_old",            # 古すぎる
    "low_quality",        # 品質不足
    "off_brand",          # ブランド不適合
    "other",              # その他
]


class QueueManager:
    """収集ツイートのキュー管理"""

    def __init__(self, queue_dir: Path | None = None):
        self._queue_dir = queue_dir or QUEUE_DIR
        self._pending_file = self._queue_dir / "pending_tweets.json"
        self._processed_file = self._queue_dir / "processed_tweets.json"

        self._queue_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_file(self._pending_file)
        self._ensure_file(self._processed_file)

    @staticmethod
    def _ensure_file(path: Path):
        """ファイルが存在しなければ空配列で初期化"""
        if not path.exists():
            with open(path, "w", encoding="utf-8") as f:
                json.dump([], f)

    @staticmethod
    def _load(path: Path) -> list[dict]:
        from src.utils import safe_json_load
        return safe_json_load(path)

    @staticmethod
    def _save(path: Path, data: list[dict]):
        from src.utils import atomic_json_save
        atomic_json_save(path, data)

    # === 追加 ===

    def add(self, tweet: ParsedTweet) -> bool:
        """
        キューにツイートを追加

        Returns:
            True: 追加成功, False: 重複のためスキップ
        """
        pending = self._load(self._pending_file)
        processed = self._load(self._processed_file)

        # 重複チェック（pending + processed）
        all_ids = {item["tweet_id"] for item in pending}
        all_ids.update(item["tweet_id"] for item in processed)

        if tweet.tweet_id in all_ids:
            return False

        # キューに追加
        entry = tweet.to_dict()
        entry["status"] = "pending"  # pending → approved → posted / skipped
        entry["added_at"] = datetime.now(JST).isoformat()
        entry["generated_text"] = ""  # 生成後に埋める
        entry["template_id"] = ""     # 使用テンプレートID
        entry["score"] = None         # スコアリング結果
        # 選定PDCAフィードバック用
        entry["skip_reason"] = ""
        entry["feedback_note"] = ""

        pending.append(entry)
        self._save(self._pending_file, pending)
        return True

    def add_batch(self, tweets: list[ParsedTweet]) -> int:
        """複数ツイートを一括追加。追加件数を返す"""
        added = 0
        for tweet in tweets:
            if self.add(tweet):
                added += 1
        return added

    # === 取得 ===

    def get_pending(self) -> list[dict]:
        """未処理のツイートを取得"""
        pending = self._load(self._pending_file)
        return [item for item in pending if item["status"] == "pending"]

    def get_approved(self) -> list[dict]:
        """承認済みで未投稿のツイートを取得"""
        pending = self._load(self._pending_file)
        return [item for item in pending if item["status"] == "approved"]

    def get_generated(self) -> list[dict]:
        """投稿文が生成済みのツイートを取得"""
        pending = self._load(self._pending_file)
        return [
            item for item in pending
            if item["status"] == "approved" and item.get("generated_text")
        ]

    def get_all_pending(self) -> list[dict]:
        """pendingファイルの全アイテムを取得"""
        return self._load(self._pending_file)

    def get_today_posted_count(self) -> int:
        """今日の投稿済み件数を取得"""
        processed = self._load(self._processed_file)
        today = datetime.now(JST).date().isoformat()
        return sum(
            1 for item in processed
            if item.get("posted_at", "").startswith(today)
        )

    # === ステータス更新 ===

    def approve(self, tweet_id: str) -> bool:
        """ツイートを承認"""
        pending = self._load(self._pending_file)
        for item in pending:
            if item["tweet_id"] == tweet_id:
                item["status"] = "approved"
                self._save(self._pending_file, pending)
                self._record_feedback(item, "approved")
                return True
        return False

    def approve_all_pending(self) -> int:
        """全pendingを一括承認"""
        pending = self._load(self._pending_file)
        count = 0
        for item in pending:
            if item["status"] == "pending":
                item["status"] = "approved"
                count += 1
        self._save(self._pending_file, pending)
        return count

    def skip(self, tweet_id: str) -> bool:
        """ツイートをスキップ（投稿しない）"""
        return self.skip_with_reason(tweet_id)

    def skip_with_reason(self, tweet_id: str, reason: str = "", note: str = "") -> bool:
        """
        ツイートをスキップ（理由付き — 選定PDCA用）

        Args:
            tweet_id: ツイートID
            reason: スキップ理由（SKIP_REASONS参照）
            note: 自由記述のフィードバックメモ
        """
        pending = self._load(self._pending_file)
        for item in pending:
            if item["tweet_id"] == tweet_id:
                item["status"] = "skipped"
                item["skip_reason"] = reason
                item["feedback_note"] = note
                self._save(self._pending_file, pending)
                self._record_feedback(item, "skipped")
                return True
        return False

    def remove(self, tweet_id: str) -> bool:
        """ツイートをキューから完全に削除"""
        pending = self._load(self._pending_file)
        new_pending = [item for item in pending if item["tweet_id"] != tweet_id]
        if len(new_pending) < len(pending):
            self._save(self._pending_file, new_pending)
            return True
        return False

    def set_generated(self, tweet_id: str, text: str, template_id: str = "", score: dict | None = None):
        """生成済みテキストを設定"""
        pending = self._load(self._pending_file)
        for item in pending:
            if item["tweet_id"] == tweet_id:
                item["generated_text"] = text
                item["template_id"] = template_id
                item["score"] = score
                break
        self._save(self._pending_file, pending)

    def mark_posted(self, tweet_id: str, posted_tweet_id: str):
        """投稿完了マーク"""
        pending = self._load(self._pending_file)
        processed = self._load(self._processed_file)

        for i, item in enumerate(pending):
            if item["tweet_id"] == tweet_id:
                item["status"] = "posted"
                item["posted_tweet_id"] = posted_tweet_id
                item["posted_at"] = datetime.now(JST).isoformat()

                # processedに移動
                processed.append(item)
                pending.pop(i)
                break

        self._save(self._pending_file, pending)
        self._save(self._processed_file, processed)

    def _update_status(self, tweet_id: str, new_status: str) -> bool:
        """ステータスを更新"""
        pending = self._load(self._pending_file)
        for item in pending:
            if item["tweet_id"] == tweet_id:
                item["status"] = new_status
                self._save(self._pending_file, pending)
                return True
        return False

    # === フィードバック記録（選定PDCA） ===

    def _record_feedback(self, item: dict, decision: str):
        """
        承認/スキップ判断をフィードバックデータに記録

        Args:
            item: キューアイテム
            decision: "approved" or "skipped"
        """
        feedback_file = FEEDBACK_FILE
        feedback_file.parent.mkdir(parents=True, exist_ok=True)

        # フィードバックデータ読み込み
        try:
            with open(feedback_file, "r", encoding="utf-8") as f:
                feedback_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            feedback_data = {"entries": [], "stats": {
                "total": 0, "approved": 0, "skipped": 0,
                "approval_rate": 0.0,
                "by_source": {}, "by_topic": {}, "by_keyword": {}, "by_reason": {},
            }}

        # エントリ追加
        entry = {
            "tweet_id": item.get("tweet_id", ""),
            "author_username": item.get("author_username", ""),
            "decision": decision,
            "skip_reason": item.get("skip_reason", ""),
            "feedback_note": item.get("feedback_note", ""),
            "preference_match_score": item.get("preference_match_score", 0.0),
            "matched_topics": item.get("matched_topics", []),
            "matched_keywords": item.get("matched_keywords", []),
            "likes": item.get("likes", 0),
            "decided_at": datetime.now(JST).isoformat(),
        }
        feedback_data["entries"].append(entry)

        # 統計更新
        stats = feedback_data.get("stats", {})
        stats["total"] = stats.get("total", 0) + 1
        stats[decision] = stats.get(decision, 0) + 1
        total = stats["total"]
        stats["approval_rate"] = round(stats.get("approved", 0) / total, 3) if total else 0.0

        # ソース別統計
        source = item.get("author_username", "unknown")
        by_source = stats.setdefault("by_source", {})
        src_stats = by_source.setdefault(source, {"approved": 0, "skipped": 0})
        src_stats[decision] = src_stats.get(decision, 0) + 1

        # トピック別統計
        by_topic = stats.setdefault("by_topic", {})
        for topic in item.get("matched_topics", []):
            topic_stats = by_topic.setdefault(topic, {"approved": 0, "skipped": 0})
            topic_stats[decision] = topic_stats.get(decision, 0) + 1

        # キーワード別統計
        by_keyword = stats.setdefault("by_keyword", {})
        for keyword in item.get("matched_keywords", []):
            kw_stats = by_keyword.setdefault(keyword, {"approved": 0, "skipped": 0})
            kw_stats[decision] = kw_stats.get(decision, 0) + 1

        # スキップ理由別統計
        if decision == "skipped" and item.get("skip_reason"):
            by_reason = stats.setdefault("by_reason", {})
            reason = item["skip_reason"]
            by_reason[reason] = by_reason.get(reason, 0) + 1

        feedback_data["stats"] = stats

        # 保存
        with open(feedback_file, "w", encoding="utf-8") as f:
            json.dump(feedback_data, f, ensure_ascii=False, indent=2)

    def get_feedback_stats(self) -> dict:
        """フィードバック統計を取得"""
        try:
            with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("stats", {})
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    # === クリーンアップ ===

    def cleanup_old(self, days: int = 7):
        """古い処理済みデータを削除"""
        processed = self._load(self._processed_file)
        cutoff = datetime.now(JST).isoformat()[:10]  # 簡易日付比較

        # daysで足切り（簡易実装）
        from datetime import timedelta
        cutoff_date = (datetime.now(JST) - timedelta(days=days)).isoformat()

        cleaned = [
            item for item in processed
            if item.get("posted_at", item.get("added_at", "")) >= cutoff_date
        ]
        self._save(self._processed_file, cleaned)

    # === 統計 ===

    def stats(self) -> dict:
        """キューの統計情報"""
        pending = self._load(self._pending_file)
        processed = self._load(self._processed_file)

        return {
            "pending": sum(1 for i in pending if i["status"] == "pending"),
            "approved": sum(1 for i in pending if i["status"] == "approved"),
            "skipped": sum(1 for i in pending if i["status"] == "skipped"),
            "posted_total": len(processed),
            "posted_today": self.get_today_posted_count(),
        }
