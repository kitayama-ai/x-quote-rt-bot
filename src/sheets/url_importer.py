"""
X Auto Post System — スプレッドシートURL一括インポート

Google SheetsのURL収集シートから未処理URLを読み取り、
キューに一括追加する。パターンAの手動収集フロー。
"""
from src.collect.queue_manager import QueueManager
from src.collect.tweet_parser import TweetParser, is_valid_tweet_url
from src.sheets.sheets_client import SheetsClient


class URLImporter:
    """スプレッドシート → キュー のインポーター"""

    def __init__(self, sheets: SheetsClient, queue: QueueManager | None = None):
        self.sheets = sheets
        self.queue = queue or QueueManager()

    def import_urls(self, auto_approve: bool = False) -> dict:
        """
        スプシの未処理URLをキューに追加

        Args:
            auto_approve: Trueなら追加と同時に承認

        Returns:
            {
                "total": int,      # スプシの未処理URL数
                "added": int,      # キューに追加した件数
                "skipped_dup": int, # 重複でスキップした件数
                "invalid": int,    # 無効なURL件数
                "errors": [str],   # エラーメッセージ
            }
        """
        pending_urls = self.sheets.get_pending_urls()

        result = {
            "total": len(pending_urls),
            "added": 0,
            "skipped_dup": 0,
            "invalid": 0,
            "errors": [],
        }

        if not pending_urls:
            print("📭 スプレッドシートに未処理のURLがありません")
            return result

        print(f"📋 未処理URL: {len(pending_urls)}件")

        updates = []

        for item in pending_urls:
            url = item["url"]
            memo = item["memo"]
            row = item["row"]

            # URL検証
            if not is_valid_tweet_url(url):
                print(f"  ⚠️ 無効なURL (行{row}): {url[:60]}")
                result["invalid"] += 1
                updates.append({"row": row, "status": "エラー", "tweet_id": ""})
                continue

            # ParsedTweet作成
            try:
                tweet = TweetParser.from_url(url, memo=memo)
            except ValueError as e:
                print(f"  ❌ URL解析エラー (行{row}): {e}")
                result["errors"].append(str(e))
                updates.append({"row": row, "status": "エラー", "tweet_id": ""})
                continue

            # キューに追加
            added = self.queue.add(tweet)
            if added:
                result["added"] += 1
                updates.append({"row": row, "status": "済", "tweet_id": tweet.tweet_id})
                print(f"  ✅ 追加: @{tweet.author_username}/{tweet.tweet_id}")

                if auto_approve:
                    self.queue.approve(tweet.tweet_id)
            else:
                result["skipped_dup"] += 1
                updates.append({"row": row, "status": "重複", "tweet_id": tweet.tweet_id})
                print(f"  ⏭️ 重複スキップ: @{tweet.author_username}/{tweet.tweet_id}")

        # スプシのステータス一括更新
        if updates:
            try:
                self.sheets.mark_urls_batch(updates)
                print(f"\n📝 スプレッドシートのステータスを{len(updates)}件更新しました")
            except Exception as e:
                print(f"\n⚠️ スプレッドシートのステータス更新エラー: {e}")

        return result

    def format_result(self, result: dict) -> str:
        """結果をフォーマット"""
        lines = [
            "📊 URL一括インポート結果:",
            f"  スプシ未処理: {result['total']}件",
            f"  キュー追加:   {result['added']}件",
            f"  重複スキップ: {result['skipped_dup']}件",
            f"  無効URL:     {result['invalid']}件",
        ]
        if result["errors"]:
            lines.append(f"  エラー:      {len(result['errors'])}件")
        return "\n".join(lines)
