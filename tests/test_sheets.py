"""
テスト — Google Sheets連携（SheetsClient + URLImporter）

gspread APIはモック化してテスト。
"""
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from src.sheets.url_importer import URLImporter


# ============================================================
# URLImporter テスト（SheetsClientはモック）
# ============================================================
class TestURLImporter:
    """スプシ→キュー インポートのテスト"""

    @pytest.fixture
    def mock_sheets(self):
        """モックSheetsClient"""
        sheets = MagicMock()
        return sheets

    @pytest.fixture
    def queue(self, tmp_path):
        """テスト用QueueManager"""
        from src.collect.queue_manager import QueueManager
        return QueueManager(queue_dir=tmp_path)

    @pytest.fixture
    def importer(self, mock_sheets, queue):
        return URLImporter(sheets=mock_sheets, queue=queue)

    def test_no_pending_urls(self, importer, mock_sheets):
        """未処理URLなし"""
        mock_sheets.get_pending_urls.return_value = []
        result = importer.import_urls()
        assert result["total"] == 0
        assert result["added"] == 0

    def test_valid_urls(self, importer, mock_sheets):
        """正常なURLをインポート"""
        mock_sheets.get_pending_urls.return_value = [
            {"row": 2, "url": "https://x.com/sama/status/111", "memo": "test1"},
            {"row": 3, "url": "https://x.com/ylecun/status/222", "memo": "test2"},
        ]
        result = importer.import_urls()
        assert result["total"] == 2
        assert result["added"] == 2
        assert result["invalid"] == 0
        mock_sheets.mark_urls_batch.assert_called_once()

    def test_invalid_url(self, importer, mock_sheets):
        """無効なURLをスキップ"""
        mock_sheets.get_pending_urls.return_value = [
            {"row": 2, "url": "https://google.com/not-a-tweet", "memo": ""},
        ]
        result = importer.import_urls()
        assert result["invalid"] == 1
        assert result["added"] == 0

    def test_duplicate_url(self, importer, mock_sheets, queue):
        """重複URLをスキップ"""
        # 先に1件追加
        from src.collect.tweet_parser import TweetParser
        tweet = TweetParser.from_url("https://x.com/sama/status/333")
        queue.add(tweet)

        mock_sheets.get_pending_urls.return_value = [
            {"row": 2, "url": "https://x.com/sama/status/333", "memo": ""},
        ]
        result = importer.import_urls()
        assert result["skipped_dup"] == 1
        assert result["added"] == 0

    def test_auto_approve(self, importer, mock_sheets, queue):
        """auto_approveで自動承認"""
        mock_sheets.get_pending_urls.return_value = [
            {"row": 2, "url": "https://x.com/sama/status/444", "memo": ""},
        ]
        result = importer.import_urls(auto_approve=True)
        assert result["added"] == 1
        assert queue.stats()["approved"] == 1

    def test_mixed_urls(self, importer, mock_sheets):
        """正常・無効・重複が混在"""
        mock_sheets.get_pending_urls.return_value = [
            {"row": 2, "url": "https://x.com/user1/status/100", "memo": "ok"},
            {"row": 3, "url": "https://example.com", "memo": "invalid"},
            {"row": 4, "url": "https://x.com/user2/status/200", "memo": "ok too"},
        ]
        result = importer.import_urls()
        assert result["added"] == 2
        assert result["invalid"] == 1

    def test_format_result(self, importer):
        """結果フォーマット"""
        result = {
            "total": 10,
            "added": 7,
            "skipped_dup": 2,
            "invalid": 1,
            "errors": [],
        }
        text = importer.format_result(result)
        assert "7" in text
        assert "2" in text
        assert "1" in text

    def test_sheets_batch_update_error(self, importer, mock_sheets):
        """スプシ更新エラーでもクラッシュしない"""
        mock_sheets.get_pending_urls.return_value = [
            {"row": 2, "url": "https://x.com/test/status/555", "memo": ""},
        ]
        mock_sheets.mark_urls_batch.side_effect = Exception("API error")
        result = importer.import_urls()
        assert result["added"] == 1  # キュー追加は成功

    def test_twitter_url_format(self, importer, mock_sheets):
        """twitter.com形式のURLも受付"""
        mock_sheets.get_pending_urls.return_value = [
            {"row": 2, "url": "https://twitter.com/OpenAI/status/666", "memo": ""},
        ]
        result = importer.import_urls()
        assert result["added"] == 1

    def test_vxtwitter_url_format(self, importer, mock_sheets):
        """vxtwitter.com形式のURLも受付"""
        mock_sheets.get_pending_urls.return_value = [
            {"row": 2, "url": "https://vxtwitter.com/AndrewYNg/status/777", "memo": ""},
        ]
        result = importer.import_urls()
        assert result["added"] == 1


# ============================================================
# CLIコマンド登録テスト
# ============================================================
class TestSheetsCommands:
    def test_import_urls_command_exists(self):
        import src.main as m
        assert hasattr(m, "cmd_import_urls")

    def test_setup_sheets_command_exists(self):
        import src.main as m
        assert hasattr(m, "cmd_setup_sheets")

    def test_commands_registered(self):
        import inspect
        import src.main as m
        source = inspect.getsource(m.main)
        assert '"import-urls"' in source
        assert '"setup-sheets"' in source
