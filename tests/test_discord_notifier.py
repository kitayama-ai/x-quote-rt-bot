"""
テスト — Discord通知（全メソッド）
"""
import pytest
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

from src.notify.discord_notifier import DiscordNotifier


@dataclass
class MockScoreResult:
    total: int = 7
    rank: str = "A"
    hook: int = 2
    specificity: int = 2
    humanity: int = 2
    structure: int = 1
    cta: int = 0
    penalty: int = 0


@dataclass
class MockSafetyResult:
    is_safe: bool = True
    violations: list = None
    warnings: list = None

    def __post_init__(self):
        self.violations = self.violations or []
        self.warnings = self.warnings or []


class TestDiscordNotifier:
    """Discord通知のテスト"""

    @pytest.fixture
    def notifier(self):
        return DiscordNotifier("https://discord.com/api/webhooks/fake/token")

    @pytest.fixture
    def notifier_no_url(self):
        return DiscordNotifier("")

    # === 基本送信 ===

    @patch("src.notify.discord_notifier.requests.post")
    def test_send_success(self, mock_post, notifier):
        """正常送信"""
        mock_post.return_value = MagicMock(status_code=204)
        result = notifier.send(content="test message")
        assert result is True
        mock_post.assert_called_once()

    @patch("src.notify.discord_notifier.requests.post")
    def test_send_with_embeds(self, mock_post, notifier):
        """Embed付き送信"""
        mock_post.return_value = MagicMock(status_code=204)
        embeds = [{"title": "Test", "color": 0x00FF00}]
        result = notifier.send(embeds=embeds)
        assert result is True

    def test_send_no_webhook(self, notifier_no_url):
        """Webhook URLなしでスキップ"""
        result = notifier_no_url.send(content="test")
        assert result is False

    @patch("src.notify.discord_notifier.requests.post")
    def test_send_error(self, mock_post, notifier):
        """送信エラー"""
        mock_post.side_effect = Exception("Network error")
        result = notifier.send(content="test")
        assert result is False

    # === notify_daily_posts ===

    @patch("src.notify.discord_notifier.requests.post")
    def test_notify_daily_posts(self, mock_post, notifier):
        """日次投稿案通知"""
        mock_post.return_value = MagicMock(status_code=204)
        posts = [
            {
                "text": "テスト投稿1",
                "type": "original",
                "time": "07:00",
                "score": MockScoreResult(total=7, rank="A"),
                "safety": MockSafetyResult(is_safe=True),
            },
            {
                "text": "テスト投稿2",
                "type": "quote_rt",
                "time": "12:00",
                "score": MockScoreResult(total=5, rank="B"),
                "safety": MockSafetyResult(is_safe=False, violations=["NGワード検出"]),
            },
        ]
        result = notifier.notify_daily_posts("テストアカウント", "@test_handle", posts)
        assert result is True

    # === notify_post_completed ===

    @patch("src.notify.discord_notifier.requests.post")
    def test_notify_post_completed(self, mock_post, notifier):
        mock_post.return_value = MagicMock(status_code=204)
        result = notifier.notify_post_completed("テスト", "テスト投稿です", "1234567890")
        assert result is True

    # === notify_safety_alert ===

    @patch("src.notify.discord_notifier.requests.post")
    def test_notify_safety_alert(self, mock_post, notifier):
        mock_post.return_value = MagicMock(status_code=204)
        result = notifier.notify_safety_alert("テスト", "NGワード含む投稿", ["NGワード検出: 不労所得"])
        assert result is True

    # === notify_metrics ===

    @patch("src.notify.discord_notifier.requests.post")
    def test_notify_metrics(self, mock_post, notifier):
        mock_post.return_value = MagicMock(status_code=204)
        metrics = {
            "followers": 1200,
            "avg_likes": 45,
            "avg_retweets": 12,
            "engagement_rate": 3.5,
        }
        result = notifier.notify_metrics("テスト", metrics)
        assert result is True

    # === notify_error ===

    @patch("src.notify.discord_notifier.requests.post")
    def test_notify_error(self, mock_post, notifier):
        mock_post.return_value = MagicMock(status_code=204)
        result = notifier.notify_error("API Error", "Connection timeout")
        assert result is True

    # === notify_weekly_report ===

    @patch("src.notify.discord_notifier.requests.post")
    def test_notify_weekly_report(self, mock_post, notifier):
        mock_post.return_value = MagicMock(status_code=204)
        result = notifier.notify_weekly_report("テスト", "週次レポート内容: フォロワー+50, エンゲージメント率3.2%")
        assert result is True

    # === notify_curate_results ===

    @patch("src.notify.discord_notifier.requests.post")
    def test_notify_curate_results(self, mock_post, notifier):
        mock_post.return_value = MagicMock(status_code=204)
        results = [
            {
                "text": "引用RTコメント",
                "template_id": "breaking_news",
                "score": MockScoreResult(total=7, rank="A"),
                "author_username": "sama",
                "original_text": "GPT-5 is here",
            }
        ]
        plan = [
            {"time": "08:30", "type": "quote_rt", "slot_id": "slot_02"},
            {"time": "12:00", "type": "original", "slot_id": "slot_04"},
        ]
        result = notifier.notify_curate_results("テスト", results, plan)
        assert result is True

    @patch("src.notify.discord_notifier.requests.post")
    def test_notify_curate_results_no_plan(self, mock_post, notifier):
        """プランなしでも動作"""
        mock_post.return_value = MagicMock(status_code=204)
        results = [{"text": "コメント", "template_id": "t1", "author_username": "u1", "original_text": "orig"}]
        result = notifier.notify_curate_results("テスト", results)
        assert result is True

    # === notify_collect_results ===

    @patch("src.notify.discord_notifier.requests.post")
    def test_notify_collect_results(self, mock_post, notifier):
        mock_post.return_value = MagicMock(status_code=204)
        collect_result = {
            "fetched": 50,
            "filtered": 20,
            "added": 15,
            "skipped_dup": 5,
        }
        result = notifier.notify_collect_results(collect_result)
        assert result is True

    @patch("src.notify.discord_notifier.requests.post")
    def test_notify_collect_results_with_tweets(self, mock_post, notifier):
        """ツイートリスト付き"""
        mock_post.return_value = MagicMock(status_code=204)

        class FakeTweet:
            def __init__(self):
                self.author_username = "testuser"
                self.likes = 50000
                self.text = "AI is amazing and transforming everything"

        collect_result = {"fetched": 10, "filtered": 5, "added": 3, "skipped_dup": 2}
        result = notifier.notify_collect_results(collect_result, tweets=[FakeTweet()])
        assert result is True

    # === notify_queue_warning ===

    @patch("src.notify.discord_notifier.requests.post")
    def test_queue_warning_empty_queue(self, mock_post, notifier):
        """キュー空 → 警告送信"""
        mock_post.return_value = MagicMock(status_code=204)
        stats = {"pending": 0, "approved": 0, "posted_today": 3}
        result = notifier.notify_queue_warning(stats)
        assert result is True
        mock_post.assert_called_once()

    def test_queue_warning_has_items(self, notifier):
        """キューに残量あり → 何もしない"""
        stats = {"pending": 5, "approved": 3, "posted_today": 2}
        result = notifier.notify_queue_warning(stats)
        assert result is True  # 問題なしでTrue

    # === Embed カラー定数 ===

    def test_color_constants(self):
        assert DiscordNotifier.COLOR_SUCCESS == 0x00D26A
        assert DiscordNotifier.COLOR_WARNING == 0xFFAA00
        assert DiscordNotifier.COLOR_DANGER == 0xFF4444
        assert DiscordNotifier.COLOR_INFO == 0x4DB8FF
        assert DiscordNotifier.COLOR_PURPLE == 0x9B59B6
