"""
X Auto Post System — キュー <-> スプレッドシート 双方向同期

GitHub Actions から呼ばれ、以下の同期を行う:
  sync_to_sheet():   queue JSON -> スプシ「キュー管理」シート
  sync_from_sheet(): スプシ「キュー管理」シート -> queue JSON (承認/拒否反映)
  sync_dashboard():  キュー統計 -> スプシ「ダッシュボード」シート
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from src.collect.queue_manager import QueueManager
from src.sheets.sheets_client import SheetsClient

JST = ZoneInfo("Asia/Tokyo")


class QueueSync:
    """キュー <-> スプレッドシート 双方向同期"""

    def __init__(
        self,
        sheets: SheetsClient,
        queue: QueueManager | None = None,
    ):
        self.sheets = sheets
        self.queue = queue or QueueManager()

    def sync_to_sheet(self) -> dict:
        """
        queue JSON -> スプシ「キュー管理」シートに同期

        pendingファイルの全アイテムをスプシに書き出す。

        Returns:
            {"synced": int, "statuses": {"pending": int, "approved": int, ...}}
        """
        all_items = self.queue.get_all_pending()

        statuses = {}
        for item in all_items:
            s = item.get("status", "unknown")
            statuses[s] = statuses.get(s, 0) + 1

        self.sheets.write_queue_items(all_items)

        return {
            "synced": len(all_items),
            "statuses": statuses,
        }

    def sync_from_sheet(self) -> dict:
        """
        スプシ「キュー管理」シート -> queue JSON に承認/拒否を反映

        pending→approved / pending→skipped の変更のみ許可。

        Returns:
            {"approved": int, "skipped": int, "unchanged": int, "errors": [str]}
        """
        decisions = self.sheets.read_queue_decisions()
        current_items = self.queue.get_all_pending()
        current_map = {item["tweet_id"]: item for item in current_items}

        result = {
            "approved": 0,
            "skipped": 0,
            "unchanged": 0,
            "errors": [],
        }

        for decision in decisions:
            tweet_id = decision["tweet_id"]
            new_status = decision["status"]

            if tweet_id not in current_map:
                continue

            current_status = current_map[tweet_id]["status"]

            if current_status == new_status:
                result["unchanged"] += 1
                continue

            # pending -> approved
            if current_status == "pending" and new_status == "approved":
                if self.queue.approve(tweet_id):
                    result["approved"] += 1
                else:
                    result["errors"].append(f"承認失敗: {tweet_id}")

            # * -> skipped
            elif new_status == "skipped":
                if self.queue.skip(tweet_id):
                    result["skipped"] += 1
                else:
                    result["errors"].append(f"スキップ失敗: {tweet_id}")
            else:
                result["unchanged"] += 1

        return result

    def sync_dashboard(self, collection_result: dict | None = None) -> dict:
        """
        ダッシュボードシートを更新

        Args:
            collection_result: 直近のcollect結果 (optional)
        """
        stats = self.queue.stats()
        now = datetime.now(JST).strftime("%Y/%m/%d %H:%M")

        dashboard = {
            "last_collection": now if collection_result else "—",
            "collected_today": (
                collection_result.get("added", 0) if collection_result else 0
            ),
            "pending": stats["pending"],
            "approved": stats["approved"],
            "posted_today": stats["posted_today"],
            "api_status": "OK",
        }

        self.sheets.update_dashboard(dashboard)
        return dashboard

    def sync_collection_log(self, result: dict):
        """収集ログシートに結果を追記"""
        self.sheets.append_collection_log({
            "fetched": result.get("fetched", 0),
            "filtered": result.get("filtered", 0),
            "added": result.get("added", 0),
            "skipped_dup": result.get("skipped_dup", 0),
            "error": "",
        })

    def full_sync(self) -> dict:
        """
        完全同期: from_sheet -> to_sheet -> dashboard

        Returns:
            {"from_sheet": {...}, "to_sheet": {...}, "dashboard": {...}}
        """
        from_result = self.sync_from_sheet()
        to_result = self.sync_to_sheet()
        dashboard = self.sync_dashboard()

        return {
            "from_sheet": from_result,
            "to_sheet": to_result,
            "dashboard": dashboard,
        }

    def read_settings(self) -> dict:
        """
        設定シートから設定を読み取り、型変換して返す

        Returns:
            {"min_likes": int, "auto_approve": bool, ...}
        """
        raw = self.sheets.get_settings()

        settings = {}
        for key in ("min_likes", "max_tweets", "max_age_hours",
                     "daily_post_limit", "auto_post_min_score"):
            if key in raw:
                try:
                    settings[key] = int(raw[key])
                except (ValueError, TypeError):
                    pass

        for key in ("auto_approve",):
            if key in raw:
                settings[key] = raw[key].lower() in ("true", "1", "yes")

        for key in ("mode",):
            if key in raw:
                settings[key] = raw[key]

        return settings
