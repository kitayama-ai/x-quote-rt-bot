"""
テスト — バズツイート収集（パターンB）
SocialDataClient, AutoCollector, TweetParser, QueueManager
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.collect.tweet_parser import TweetParser, ParsedTweet, is_valid_tweet_url
from src.collect.queue_manager import QueueManager
from src.collect.socialdata_client import SocialDataClient, SocialDataError


# ========================================
# TweetParser Tests
# ========================================

class TestTweetParser:
    def test_parse_x_url(self):
        """x.com URLをパース"""
        result = TweetParser.parse_url("https://x.com/sama/status/1234567890")
        assert result == ("sama", "1234567890")

    def test_parse_twitter_url(self):
        """twitter.com URLをパース"""
        result = TweetParser.parse_url("https://twitter.com/karpathy/status/9876543210")
        assert result == ("karpathy", "9876543210")

    def test_parse_mobile_url(self):
        """モバイルURLをパース"""
        result = TweetParser.parse_url("https://mobile.twitter.com/AndrewYNg/status/1111111111")
        assert result == ("AndrewYNg", "1111111111")

    def test_parse_vx_url(self):
        """vxtwitter URLをパース"""
        result = TweetParser.parse_url("https://vxtwitter.com/sama/status/5555555555")
        assert result == ("sama", "5555555555")

    def test_parse_url_with_query_params(self):
        """クエリパラメータ付きURLをパース"""
        result = TweetParser.parse_url("https://x.com/sama/status/1234567890?s=20&t=abc")
        assert result == ("sama", "1234567890")

    def test_parse_invalid_url(self):
        """無効なURLはNone"""
        assert TweetParser.parse_url("https://google.com") is None
        assert TweetParser.parse_url("not a url") is None
        assert TweetParser.parse_url("") is None

    def test_extract_tweet_id(self):
        """ツイートIDのみ抽出"""
        assert TweetParser.extract_tweet_id("https://x.com/sama/status/12345") == "12345"
        assert TweetParser.extract_tweet_id("invalid") is None

    def test_build_url(self):
        """URL構築"""
        url = TweetParser.build_url("sama", "12345")
        assert url == "https://x.com/sama/status/12345"

    def test_from_url(self):
        """URLからParsedTweet生成"""
        tweet = TweetParser.from_url("https://x.com/sama/status/12345", text="hello")
        assert tweet.tweet_id == "12345"
        assert tweet.author_username == "sama"
        assert tweet.text == "hello"
        assert tweet.source == "manual"
        assert tweet.collected_at

    def test_from_url_invalid(self):
        """無効URLでValueError"""
        with pytest.raises(ValueError):
            TweetParser.from_url("https://google.com")

    def test_from_api_data(self):
        """APIデータからParsedTweet生成（SocialData形式）"""
        data = {
            "id": 9876543210,
            "full_text": "AI Agents are becoming mainstream.",
            "user": {
                "screen_name": "AndrewYNg",
                "name": "Andrew Ng",
            },
            "lang": "en",
            "favorite_count": 38700,
            "retweet_count": 8100,
            "reply_count": 500,
            "quote_count": 200,
            "bookmark_count": 1500,
        }
        tweet = TweetParser.from_api_data(data, source="socialdata")
        assert tweet.tweet_id == "9876543210"
        assert tweet.author_username == "AndrewYNg"
        assert tweet.author_name == "Andrew Ng"
        assert tweet.text == "AI Agents are becoming mainstream."
        assert tweet.likes == 38700
        assert tweet.retweets == 8100
        assert tweet.source == "socialdata"

    def test_from_api_data_text_field(self):
        """APIデータの'text'フィールドも対応"""
        data = {
            "id": 12345,
            "text": "Hello world",
            "user": {"screen_name": "test"},
            "favorite_count": 100,
        }
        tweet = TweetParser.from_api_data(data)
        assert tweet.text == "Hello world"

    def test_is_valid_tweet_url(self):
        """URL妥当性チェック"""
        assert is_valid_tweet_url("https://x.com/sama/status/12345")
        assert not is_valid_tweet_url("https://google.com")


# ========================================
# ParsedTweet Tests
# ========================================

class TestParsedTweet:
    def test_to_dict(self):
        """辞書変換"""
        tweet = ParsedTweet(tweet_id="123", author_username="test", likes=100)
        d = tweet.to_dict()
        assert d["tweet_id"] == "123"
        assert d["likes"] == 100

    def test_from_dict(self):
        """辞書から復元"""
        data = {"tweet_id": "123", "author_username": "test", "likes": 50}
        tweet = ParsedTweet.from_dict(data)
        assert tweet.tweet_id == "123"
        assert tweet.likes == 50

    def test_roundtrip(self):
        """to_dict → from_dict の往復"""
        original = ParsedTweet(
            tweet_id="999",
            author_username="sama",
            text="test tweet",
            likes=1000,
            source="socialdata",
        )
        restored = ParsedTweet.from_dict(original.to_dict())
        assert restored.tweet_id == original.tweet_id
        assert restored.text == original.text
        assert restored.source == original.source


# ========================================
# QueueManager Tests
# ========================================

@pytest.fixture
def queue_dir(tmp_path):
    """一時ディレクトリでキュー管理"""
    return tmp_path / "queue"


@pytest.fixture
def queue(queue_dir):
    return QueueManager(queue_dir=queue_dir)


class TestQueueManager:
    def test_add_tweet(self, queue):
        """ツイートをキューに追加"""
        tweet = ParsedTweet(tweet_id="001", author_username="sama", text="hello")
        assert queue.add(tweet) is True

        pending = queue.get_pending()
        assert len(pending) == 1
        assert pending[0]["tweet_id"] == "001"
        assert pending[0]["status"] == "pending"

    def test_add_duplicate(self, queue):
        """重複追加はスキップ"""
        tweet = ParsedTweet(tweet_id="001", author_username="sama")
        assert queue.add(tweet) is True
        assert queue.add(tweet) is False

    def test_add_batch(self, queue):
        """一括追加"""
        tweets = [
            ParsedTweet(tweet_id="001", author_username="a"),
            ParsedTweet(tweet_id="002", author_username="b"),
            ParsedTweet(tweet_id="001", author_username="a"),  # dup
        ]
        added = queue.add_batch(tweets)
        assert added == 2

    def test_approve(self, queue):
        """承認"""
        tweet = ParsedTweet(tweet_id="001", author_username="sama")
        queue.add(tweet)
        assert queue.approve("001") is True
        assert queue.get_approved()[0]["status"] == "approved"

    def test_approve_all_pending(self, queue):
        """一括承認"""
        for i in range(3):
            queue.add(ParsedTweet(tweet_id=f"00{i}", author_username="test"))

        count = queue.approve_all_pending()
        assert count == 3
        assert len(queue.get_approved()) == 3
        assert len(queue.get_pending()) == 0

    def test_set_generated(self, queue):
        """生成テキスト設定"""
        tweet = ParsedTweet(tweet_id="001", author_username="sama")
        queue.add(tweet)
        queue.approve("001")

        queue.set_generated("001", text="生成されたテキスト", template_id="breaking_news")
        generated = queue.get_generated()
        assert len(generated) == 1
        assert generated[0]["generated_text"] == "生成されたテキスト"
        assert generated[0]["template_id"] == "breaking_news"

    def test_mark_posted(self, queue):
        """投稿完了マーク"""
        tweet = ParsedTweet(tweet_id="001", author_username="sama")
        queue.add(tweet)
        queue.approve("001")
        queue.set_generated("001", text="test")

        queue.mark_posted("001", posted_tweet_id="posted_999")

        assert len(queue.get_all_pending()) == 0
        stats = queue.stats()
        assert stats["posted_total"] == 1

    def test_skip(self, queue):
        """スキップ"""
        tweet = ParsedTweet(tweet_id="001", author_username="sama")
        queue.add(tweet)
        assert queue.skip("001") is True

    def test_stats(self, queue):
        """統計情報"""
        queue.add(ParsedTweet(tweet_id="001", author_username="a"))
        queue.add(ParsedTweet(tweet_id="002", author_username="b"))
        queue.add(ParsedTweet(tweet_id="003", author_username="c"))
        queue.approve("002")
        queue.skip("003")

        stats = queue.stats()
        assert stats["pending"] == 1
        assert stats["approved"] == 1
        assert stats["skipped"] == 1


# ========================================
# SocialDataClient Tests
# ========================================

class TestSocialDataClient:
    def test_init_no_key(self):
        """APIキーなしでValueError"""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="SOCIALDATA_API_KEY"):
                SocialDataClient(api_key="")

    def test_init_with_key(self):
        """APIキー指定で初期化"""
        client = SocialDataClient(api_key="test_key_123")
        assert client.api_key == "test_key_123"

    def test_init_from_env(self):
        """環境変数からAPIキー取得"""
        with patch.dict("os.environ", {"SOCIALDATA_API_KEY": "env_key_456"}):
            client = SocialDataClient()
            assert client.api_key == "env_key_456"

    def test_build_search_query_accounts(self):
        """アカウント検索クエリ生成"""
        client = SocialDataClient(api_key="test")
        query = client.build_search_query(
            accounts=["sama", "karpathy"],
            min_likes=1000,
            lang="en",
        )
        assert "from:sama" in query
        assert "from:karpathy" in query
        assert "min_faves:1000" in query
        assert "lang:en" in query
        assert "-filter:replies" in query
        assert "-filter:retweets" in query

    def test_build_search_query_keywords(self):
        """キーワード検索クエリ生成"""
        client = SocialDataClient(api_key="test")
        query = client.build_search_query(
            keywords=["AI agent", "LLM"],
            min_likes=500,
        )
        assert '"AI agent"' in query
        assert "LLM" in query
        assert "min_faves:500" in query

    def test_build_search_query_keywords_ignored_when_accounts(self):
        """アカウント指定時はキーワード無視"""
        client = SocialDataClient(api_key="test")
        query = client.build_search_query(
            accounts=["sama"],
            keywords=["AI"],
            min_likes=500,
        )
        assert "from:sama" in query
        assert "AI" not in query  # keywords should be ignored

    @patch("src.collect.socialdata_client.requests.Session")
    def test_search_tweets_success(self, mock_session_cls):
        """検索成功"""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tweets": [
                {"id": 1, "full_text": "tweet 1", "user": {"screen_name": "a"}},
                {"id": 2, "full_text": "tweet 2", "user": {"screen_name": "b"}},
            ],
            "next_cursor": None,
        }
        mock_session.request.return_value = mock_response

        client = SocialDataClient(api_key="test")
        client.session = mock_session

        tweets = client.search_tweets("from:sama", max_results=10)
        assert len(tweets) == 2

    @patch("src.collect.socialdata_client.requests.Session")
    def test_search_tweets_rate_limit(self, mock_session_cls):
        """レート制限エラー"""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_session.request.return_value = mock_response

        client = SocialDataClient(api_key="test")
        client.session = mock_session

        with pytest.raises(SocialDataError) as exc_info:
            client.search_tweets("from:sama")
        assert exc_info.value.status_code == 429

    @patch("src.collect.socialdata_client.requests.Session")
    def test_search_tweets_auth_error(self, mock_session_cls):
        """認証エラー"""
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_session.request.return_value = mock_response

        client = SocialDataClient(api_key="test")
        client.session = mock_session

        with pytest.raises(SocialDataError) as exc_info:
            client.search_tweets("from:sama")
        assert exc_info.value.status_code == 401


# ========================================
# AutoCollector Tests
# ========================================

class TestAutoCollector:
    @patch("src.collect.auto_collector.SocialDataClient")
    def test_collect_dry_run(self, mock_client_cls, queue):
        """ドライラン収集"""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_client.build_search_query.return_value = "from:sama min_faves:500"
        mock_client.search_tweets.return_value = [
            {
                "id": 12345,
                "full_text": "This is a test tweet about AI agents.",
                "user": {"screen_name": "sama", "name": "Sam Altman"},
                "favorite_count": 50000,
                "retweet_count": 10000,
                "lang": "en",
                "created_at": "Thu Feb 18 02:14:30 +0000 2026",
            },
        ]

        from src.collect.auto_collector import AutoCollector
        collector = AutoCollector.__new__(AutoCollector)
        collector.client = mock_client
        collector.queue = queue
        collector.target_accounts = [{"username": "sama", "priority": "high"}]
        collector.keywords = []
        collector.buzz_thresholds = {"likes_min": 500, "lang": ["en"], "age_max_hours": 48}

        result = collector.collect(dry_run=True)

        assert result["fetched"] == 1
        assert result["filtered"] == 1
        assert result["added"] == 1
        # dry_runなのでキューには追加されない
        assert len(queue.get_pending()) == 0

    @patch("src.collect.auto_collector.SocialDataClient")
    def test_collect_with_auto_approve(self, mock_client_cls, queue):
        """自動承認付き収集"""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_client.build_search_query.return_value = "from:sama min_faves:500"
        mock_client.search_tweets.return_value = [
            {
                "id": 99999,
                "full_text": "AI is amazing and transformative.",
                "user": {"screen_name": "karpathy", "name": "Andrej Karpathy"},
                "favorite_count": 30000,
                "retweet_count": 5000,
                "lang": "en",
                "created_at": "Thu Feb 18 02:14:30 +0000 2026",
            },
        ]

        from src.collect.auto_collector import AutoCollector
        collector = AutoCollector.__new__(AutoCollector)
        collector.client = mock_client
        collector.queue = queue
        collector.target_accounts = [{"username": "karpathy", "priority": "high"}]
        collector.keywords = []
        collector.buzz_thresholds = {"likes_min": 500, "lang": ["en"], "age_max_hours": 48}

        result = collector.collect(auto_approve=True)

        assert result["added"] == 1
        assert len(queue.get_approved()) == 1

    @patch("src.collect.auto_collector.SocialDataClient")
    def test_collect_filters_replies(self, mock_client_cls, queue):
        """リプライはフィルタされる"""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_client.build_search_query.return_value = "from:sama"
        mock_client.search_tweets.return_value = [
            {
                "id": 11111,
                "full_text": "This is a reply",
                "user": {"screen_name": "test"},
                "favorite_count": 50000,
                "lang": "en",
                "in_reply_to_status_id": "99999",
                "created_at": "Thu Feb 18 02:14:30 +0000 2026",
            },
        ]

        from src.collect.auto_collector import AutoCollector
        collector = AutoCollector.__new__(AutoCollector)
        collector.client = mock_client
        collector.queue = queue
        collector.target_accounts = [{"username": "test", "priority": "medium"}]
        collector.keywords = []
        collector.buzz_thresholds = {"likes_min": 500, "lang": ["en"], "age_max_hours": 48}

        result = collector.collect()
        assert result["filtered"] == 0

    @patch("src.collect.auto_collector.SocialDataClient")
    def test_collect_filters_retweets(self, mock_client_cls, queue):
        """RTはフィルタされる"""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_client.build_search_query.return_value = "from:test"
        mock_client.search_tweets.return_value = [
            {
                "id": 22222,
                "full_text": "RT @someone: Original tweet",
                "user": {"screen_name": "test"},
                "favorite_count": 50000,
                "lang": "en",
                "created_at": "Thu Feb 18 02:14:30 +0000 2026",
            },
        ]

        from src.collect.auto_collector import AutoCollector
        collector = AutoCollector.__new__(AutoCollector)
        collector.client = mock_client
        collector.queue = queue
        collector.target_accounts = [{"username": "test", "priority": "medium"}]
        collector.keywords = []
        collector.buzz_thresholds = {"likes_min": 500, "lang": ["en"], "age_max_hours": 48}

        result = collector.collect()
        assert result["filtered"] == 0

    def test_format_result(self, queue):
        """結果フォーマット"""
        from src.collect.auto_collector import AutoCollector
        collector = AutoCollector.__new__(AutoCollector)
        collector.queue = queue

        result = {
            "fetched": 30,
            "filtered": 10,
            "added": 8,
            "skipped_dup": 2,
            "tweets": [
                ParsedTweet(tweet_id="1", author_username="sama", text="Hello world tweet", likes=50000),
            ],
        }
        formatted = collector.format_result(result)
        assert "30" in formatted
        assert "10" in formatted
        assert "8" in formatted
        assert "sama" in formatted
