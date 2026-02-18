"""
テスト — QueueSync (キュー <-> スプレッドシート同期)

SheetsClientはモック化してテスト。
"""
import pytest
from unittest.mock import MagicMock

from src.collect.queue_manager import QueueManager
from src.collect.tweet_parser import ParsedTweet
from src.sheets.queue_sync import QueueSync


def _make_tweet(tweet_id: str, username: str = "test_user") -> ParsedTweet:
    return ParsedTweet(
        tweet_id=tweet_id,
        author_username=username,
        text=f"Test tweet {tweet_id}",
        likes=1000,
        source="socialdata",
    )


@pytest.fixture
def tmp_queue(tmp_path):
    return QueueManager(queue_dir=tmp_path)


@pytest.fixture
def mock_sheets():
    mock = MagicMock()
    mock.write_queue_items = MagicMock()
    mock.read_queue_decisions = MagicMock(return_value=[])
    mock.append_collection_log = MagicMock()
    mock.update_dashboard = MagicMock()
    mock.get_settings = MagicMock(return_value={})
    return mock


@pytest.fixture
def sync(mock_sheets, tmp_queue):
    return QueueSync(sheets=mock_sheets, queue=tmp_queue)


# ============================================================
# sync_to_sheet
# ============================================================
class TestSyncToSheet:
    def test_empty_queue(self, sync, mock_sheets):
        """空のキューで同期"""
        result = sync.sync_to_sheet()
        assert result["synced"] == 0
        mock_sheets.write_queue_items.assert_called_once_with([])

    def test_with_items(self, sync, mock_sheets, tmp_queue):
        """アイテムのあるキューを同期"""
        tmp_queue.add(_make_tweet("111"))
        tmp_queue.add(_make_tweet("222"))

        result = sync.sync_to_sheet()
        assert result["synced"] == 2
        assert result["statuses"]["pending"] == 2

        call_args = mock_sheets.write_queue_items.call_args[0][0]
        assert len(call_args) == 2

    def test_mixed_statuses(self, sync, mock_sheets, tmp_queue):
        """様々なステータスのアイテムを同期"""
        tmp_queue.add(_make_tweet("111"))
        tmp_queue.add(_make_tweet("222"))
        tmp_queue.approve("222")

        result = sync.sync_to_sheet()
        assert result["synced"] == 2
        assert result["statuses"]["pending"] == 1
        assert result["statuses"]["approved"] == 1


# ============================================================
# sync_from_sheet
# ============================================================
class TestSyncFromSheet:
    def test_no_decisions(self, sync, mock_sheets):
        """変更なしの場合"""
        result = sync.sync_from_sheet()
        assert result["approved"] == 0
        assert result["skipped"] == 0

    def test_approve_pending(self, sync, mock_sheets, tmp_queue):
        """pending -> approved"""
        tmp_queue.add(_make_tweet("111"))
        mock_sheets.read_queue_decisions.return_value = [
            {"row": 2, "status": "approved", "tweet_id": "111"}
        ]

        result = sync.sync_from_sheet()
        assert result["approved"] == 1

        approved = tmp_queue.get_approved()
        assert len(approved) == 1
        assert approved[0]["tweet_id"] == "111"

    def test_skip_pending(self, sync, mock_sheets, tmp_queue):
        """pending -> skipped"""
        tmp_queue.add(_make_tweet("111"))
        mock_sheets.read_queue_decisions.return_value = [
            {"row": 2, "status": "skipped", "tweet_id": "111"}
        ]

        result = sync.sync_from_sheet()
        assert result["skipped"] == 1

    def test_unchanged(self, sync, mock_sheets, tmp_queue):
        """ステータスが変わっていない場合"""
        tmp_queue.add(_make_tweet("111"))
        mock_sheets.read_queue_decisions.return_value = [
            {"row": 2, "status": "pending", "tweet_id": "111"}
        ]

        result = sync.sync_from_sheet()
        assert result["unchanged"] == 1

    def test_unknown_tweet_ignored(self, sync, mock_sheets):
        """キューに存在しないtweet_idは無視"""
        mock_sheets.read_queue_decisions.return_value = [
            {"row": 2, "status": "approved", "tweet_id": "nonexistent"}
        ]

        result = sync.sync_from_sheet()
        assert result["approved"] == 0
        assert result["unchanged"] == 0

    def test_mixed_decisions(self, sync, mock_sheets, tmp_queue):
        """承認・スキップ・変更なしが混在"""
        tmp_queue.add(_make_tweet("111"))
        tmp_queue.add(_make_tweet("222"))
        tmp_queue.add(_make_tweet("333"))
        mock_sheets.read_queue_decisions.return_value = [
            {"row": 2, "status": "approved", "tweet_id": "111"},
            {"row": 3, "status": "skipped", "tweet_id": "222"},
            {"row": 4, "status": "pending", "tweet_id": "333"},
        ]

        result = sync.sync_from_sheet()
        assert result["approved"] == 1
        assert result["skipped"] == 1
        assert result["unchanged"] == 1

    def test_invalid_transition_ignored(self, sync, mock_sheets, tmp_queue):
        """approved -> pending への逆方向変更は無視"""
        tmp_queue.add(_make_tweet("111"))
        tmp_queue.approve("111")
        mock_sheets.read_queue_decisions.return_value = [
            {"row": 2, "status": "pending", "tweet_id": "111"}
        ]

        result = sync.sync_from_sheet()
        assert result["unchanged"] == 1
        # 元のapproved状態が維持されている
        approved = tmp_queue.get_approved()
        assert len(approved) == 1


# ============================================================
# full_sync
# ============================================================
class TestFullSync:
    def test_full_sync_flow(self, sync, mock_sheets, tmp_queue):
        """完全同期のフロー確認"""
        tmp_queue.add(_make_tweet("111"))
        mock_sheets.read_queue_decisions.return_value = []

        result = sync.full_sync()
        assert "from_sheet" in result
        assert "to_sheet" in result
        assert "dashboard" in result
        mock_sheets.update_dashboard.assert_called_once()

    def test_full_sync_applies_decisions_first(self, sync, mock_sheets, tmp_queue):
        """full_syncはfrom_sheetを先に実行する"""
        tmp_queue.add(_make_tweet("111"))
        mock_sheets.read_queue_decisions.return_value = [
            {"row": 2, "status": "approved", "tweet_id": "111"}
        ]

        result = sync.full_sync()
        assert result["from_sheet"]["approved"] == 1
        # to_sheetの時点ではapproved状態で同期される
        assert result["to_sheet"]["statuses"]["approved"] == 1


# ============================================================
# sync_dashboard
# ============================================================
class TestSyncDashboard:
    def test_dashboard_without_collection(self, sync, mock_sheets, tmp_queue):
        """収集結果なしのダッシュボード更新"""
        tmp_queue.add(_make_tweet("111"))

        dashboard = sync.sync_dashboard()
        assert dashboard["pending"] == 1
        assert dashboard["last_collection"] == "—"
        mock_sheets.update_dashboard.assert_called_once()

    def test_dashboard_with_collection(self, sync, mock_sheets, tmp_queue):
        """収集結果ありのダッシュボード更新"""
        dashboard = sync.sync_dashboard(collection_result={"added": 5})
        assert dashboard["collected_today"] == 5
        assert dashboard["last_collection"] != "—"


# ============================================================
# sync_collection_log
# ============================================================
class TestSyncCollectionLog:
    def test_log_appended(self, sync, mock_sheets):
        """収集ログが追記される"""
        result = {"fetched": 30, "filtered": 10, "added": 5, "skipped_dup": 2}
        sync.sync_collection_log(result)
        mock_sheets.append_collection_log.assert_called_once()
        call_arg = mock_sheets.append_collection_log.call_args[0][0]
        assert call_arg["fetched"] == 30
        assert call_arg["added"] == 5


# ============================================================
# read_settings
# ============================================================
class TestReadSettings:
    def test_empty_settings(self, sync, mock_sheets):
        """空の設定"""
        settings = sync.read_settings()
        assert settings == {}

    def test_int_conversion(self, sync, mock_sheets):
        """int型の変換"""
        mock_sheets.get_settings.return_value = {
            "min_likes": "500", "max_tweets": "30"
        }
        settings = sync.read_settings()
        assert settings["min_likes"] == 500
        assert settings["max_tweets"] == 30

    def test_bool_conversion(self, sync, mock_sheets):
        """bool型の変換"""
        mock_sheets.get_settings.return_value = {"auto_approve": "true"}
        settings = sync.read_settings()
        assert settings["auto_approve"] is True

        mock_sheets.get_settings.return_value = {"auto_approve": "false"}
        settings = sync.read_settings()
        assert settings["auto_approve"] is False

    def test_invalid_int_ignored(self, sync, mock_sheets):
        """不正なint値は無視"""
        mock_sheets.get_settings.return_value = {"min_likes": "abc"}
        settings = sync.read_settings()
        assert "min_likes" not in settings

    def test_string_settings(self, sync, mock_sheets):
        """文字列設定の読み取り"""
        mock_sheets.get_settings.return_value = {"mode": "semi_auto"}
        settings = sync.read_settings()
        assert settings["mode"] == "semi_auto"
