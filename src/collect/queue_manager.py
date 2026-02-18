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
        return self._update_status(tweet_id, "approved")

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
        return self._update_status(tweet_id, "skipped")

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
