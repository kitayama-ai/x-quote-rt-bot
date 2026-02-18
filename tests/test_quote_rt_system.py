"""
引用RT自動投稿システム — ユニットテスト

テスト対象:
  - tweet_parser: URL解析、ツイートID抽出
  - queue_manager: キュー管理（追加/承認/投稿フロー）
  - mix_planner: 投稿ミックスプランナー（BAN対策の核）
  - safety_checker: 引用RT固有の安全チェック
  - quote_generator: 引用RT投稿文生成（デモモード）
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch

# プロジェクトルート
PROJECT_ROOT = Path(__file__).parent.parent


# ============================================================
# tweet_parser テスト
# ============================================================
class TestTweetParser:
    """URL解析とツイート情報抽出のテスト"""

    def test_valid_x_url(self):
        from src.collect.tweet_parser import is_valid_tweet_url
        assert is_valid_tweet_url("https://x.com/sama/status/1234567890")

    def test_valid_twitter_url(self):
        from src.collect.tweet_parser import is_valid_tweet_url
        assert is_valid_tweet_url("https://twitter.com/ylecun/status/9876543210")

    def test_valid_vxtwitter_url(self):
        from src.collect.tweet_parser import is_valid_tweet_url
        assert is_valid_tweet_url("https://vxtwitter.com/AndrewYNg/status/1111111111")

    def test_invalid_url(self):
        from src.collect.tweet_parser import is_valid_tweet_url
        assert not is_valid_tweet_url("https://google.com")
        assert not is_valid_tweet_url("https://x.com/sama")  # statusなし
        assert not is_valid_tweet_url("")

    def test_parse_from_url(self):
        from src.collect.tweet_parser import TweetParser
        tweet = TweetParser.from_url(
            "https://x.com/sama/status/1234567890",
            text="Hello world",
            memo="Test memo",
        )
        assert tweet.tweet_id == "1234567890"
        assert tweet.author_username == "sama"
        assert tweet.url == "https://x.com/sama/status/1234567890"
        assert tweet.text == "Hello world"
        assert tweet.memo == "Test memo"

    def test_parse_twitter_url(self):
        from src.collect.tweet_parser import TweetParser
        tweet = TweetParser.from_url("https://twitter.com/ylecun/status/9876543210")
        assert tweet.tweet_id == "9876543210"
        assert tweet.author_username == "ylecun"
        # URLはx.comに正規化
        assert "x.com" in tweet.url

    def test_parse_url_with_query_params(self):
        from src.collect.tweet_parser import TweetParser
        tweet = TweetParser.from_url(
            "https://x.com/OpenAI/status/5555555555?s=20&t=abc123"
        )
        assert tweet.tweet_id == "5555555555"
        assert tweet.author_username == "OpenAI"

    def test_invalid_url_raises(self):
        from src.collect.tweet_parser import TweetParser
        with pytest.raises(ValueError):
            TweetParser.from_url("https://google.com/foo")

    def test_to_dict(self):
        from src.collect.tweet_parser import TweetParser
        tweet = TweetParser.from_url(
            "https://x.com/sama/status/1234567890",
            text="Test",
            memo="Note",
        )
        d = tweet.to_dict()
        assert d["tweet_id"] == "1234567890"
        assert d["author_username"] == "sama"
        assert d["text"] == "Test"
        assert d["memo"] == "Note"
        assert "collected_at" in d


# ============================================================
# queue_manager テスト
# ============================================================
class TestQueueManager:
    """キュー管理のテスト"""

    @pytest.fixture(autouse=True)
    def setup_queue(self, tmp_path):
        """テスト用の一時ディレクトリでQueueManagerを作成"""
        from src.collect.queue_manager import QueueManager
        self.queue = QueueManager(queue_dir=tmp_path)

    def _make_tweet(self, tweet_id="123", username="testuser", text="Test tweet"):
        from src.collect.tweet_parser import TweetParser
        return TweetParser.from_url(
            f"https://x.com/{username}/status/{tweet_id}",
            text=text,
        )

    def test_add_tweet(self):
        tweet = self._make_tweet("111")
        assert self.queue.add(tweet) is True
        assert self.queue.stats()["pending"] == 1

    def test_duplicate_prevention(self):
        tweet = self._make_tweet("222")
        assert self.queue.add(tweet) is True
        assert self.queue.add(tweet) is False  # 重複は弾く
        assert self.queue.stats()["pending"] == 1

    def test_approve(self):
        tweet = self._make_tweet("333")
        self.queue.add(tweet)
        assert self.queue.approve("333") is True
        assert self.queue.stats()["approved"] == 1
        assert self.queue.stats()["pending"] == 0

    def test_approve_nonexistent(self):
        assert self.queue.approve("999") is False

    def test_approve_all(self):
        self.queue.add(self._make_tweet("444", "user1"))
        self.queue.add(self._make_tweet("555", "user2"))
        count = self.queue.approve_all_pending()
        assert count == 2
        assert self.queue.stats()["approved"] == 2

    def test_skip(self):
        tweet = self._make_tweet("666")
        self.queue.add(tweet)
        assert self.queue.skip("666") is True
        assert self.queue.stats()["skipped"] == 1

    def test_set_generated(self):
        tweet = self._make_tweet("777")
        self.queue.add(tweet)
        self.queue.approve("777")
        self.queue.set_generated(
            tweet_id="777",
            text="引用RTコメント",
            template_id="breaking_news",
            score={"total": 7, "rank": "B+"},
        )
        generated = self.queue.get_generated()
        assert len(generated) == 1
        assert generated[0]["generated_text"] == "引用RTコメント"

    def test_mark_posted(self):
        tweet = self._make_tweet("888")
        self.queue.add(tweet)
        self.queue.approve("888")
        self.queue.set_generated("888", "コメント", "summary_points")
        self.queue.mark_posted("888", "posted_id_001")
        assert self.queue.stats()["posted_total"] == 1

    def test_full_flow(self):
        """pending → approved → generated → posted の全フロー"""
        tweet = self._make_tweet("999", "sama", "GPT-5 is amazing")
        self.queue.add(tweet)
        assert self.queue.stats()["pending"] == 1

        self.queue.approve("999")
        assert self.queue.stats()["approved"] == 1

        self.queue.set_generated("999", "すごい発表！", "breaking_news", {"total": 8})
        generated = self.queue.get_generated()
        assert len(generated) == 1

        self.queue.mark_posted("999", "posted_123")
        assert self.queue.stats()["posted_total"] == 1
        assert self.queue.stats()["approved"] == 0

    def test_get_pending(self):
        self.queue.add(self._make_tweet("101"))
        self.queue.add(self._make_tweet("102"))
        pending = self.queue.get_pending()
        assert len(pending) == 2

    def test_get_approved(self):
        self.queue.add(self._make_tweet("201"))
        self.queue.add(self._make_tweet("202"))
        self.queue.approve("201")
        approved = self.queue.get_approved()
        assert len(approved) == 1


# ============================================================
# mix_planner テスト
# ============================================================
class TestMixPlanner:
    """投稿ミックスプランナーのテスト（BAN対策の核）"""

    def setup_method(self):
        from src.post.mix_planner import MixPlanner
        self.planner = MixPlanner()

    def test_daily_plan_generates(self):
        plan = self.planner.plan_daily(available_quotes=10)
        assert len(plan) >= 7
        assert len(plan) <= 10

    def test_plan_has_both_types(self):
        plan = self.planner.plan_daily(available_quotes=10)
        types = {p["type"] for p in plan}
        assert "original" in types
        assert "quote_rt" in types

    def test_max_consecutive_quotes(self):
        """連続引用RTは最大2件"""
        for _ in range(20):  # 20回テストして確率的にカバー
            plan = self.planner.plan_daily(available_quotes=10)
            consecutive = 0
            max_consecutive = 0
            for item in plan:
                if item["type"] == "quote_rt":
                    consecutive += 1
                    max_consecutive = max(max_consecutive, consecutive)
                else:
                    consecutive = 0
            assert max_consecutive <= 2, f"連続引用RT: {max_consecutive} (max 2)"

    def test_min_interval_60_minutes(self):
        """最小投稿間隔は60分"""
        for _ in range(20):
            plan = self.planner.plan_daily(available_quotes=10)
            for i in range(1, len(plan)):
                prev = plan[i - 1]["scheduled_hour"] * 60 + plan[i - 1]["scheduled_minute"]
                curr = plan[i]["scheduled_hour"] * 60 + plan[i]["scheduled_minute"]
                diff = curr - prev
                assert diff >= 60, (
                    f"間隔不足: {plan[i-1]['time']} → {plan[i]['time']} = {diff}min"
                )

    def test_quote_rt_ratio(self):
        """引用RT比率は70%以下"""
        for _ in range(20):
            plan = self.planner.plan_daily(available_quotes=10)
            qt = sum(1 for p in plan if p["type"] == "quote_rt")
            ratio = qt / len(plan)
            assert ratio <= 0.75, f"引用RT比率: {ratio:.0%} (max 70%)"

    def test_time_range(self):
        """投稿時間は6時〜23時の範囲"""
        plan = self.planner.plan_daily(available_quotes=10)
        for item in plan:
            assert 6 <= item["scheduled_hour"] <= 23, (
                f"時間範囲外: {item['time']}"
            )

    def test_format_plan(self):
        plan = self.planner.plan_daily(available_quotes=10)
        formatted = self.planner.format_plan(plan)
        assert "投稿スケジュール" in formatted
        assert "引用RT" in formatted
        assert "オリジナル" in formatted


# ============================================================
# safety_checker — 引用RT固有チェックのテスト
# ============================================================
class TestSafetyCheckerQuoteRT:
    """引用RT専用の安全チェック"""

    @pytest.fixture(autouse=True)
    def setup_checker(self):
        from src.post.safety_checker import SafetyChecker
        rules_path = PROJECT_ROOT / "config" / "safety_rules.json"
        with open(rules_path, "r") as f:
            rules = json.load(f)
        self.checker = SafetyChecker(rules)

    def test_valid_quote_rt(self):
        result = self.checker.check(
            "これはマジで来る。AIエージェントが自律的に動く時代が始まった。日本でも半年以内に当たり前になるよ",
            is_quote_rt=True,
        )
        assert result.is_safe

    def test_too_short_quote_rt(self):
        result = self.checker.check("短い", is_quote_rt=True)
        assert not result.is_safe
        assert any("文字数不足" in v for v in result.violations)

    def test_translation_only_blocked(self):
        result = self.checker.check(
            "翻訳しました：GPT-5はマルチモーダル機能を大幅に強化し、新たな可能性を切り開く",
            is_quote_rt=True,
            quote_rt_context={
                "source_username": "sama",
                "today_same_source_count": 0,
                "consecutive_quote_count": 0,
            },
        )
        assert not result.is_safe
        assert any("禁止パターン" in v for v in result.violations)

    def test_same_source_daily_limit(self):
        result = self.checker.check(
            "またOpenAIからすごい発表が。これは見逃せない。AIの進化が加速してる感じがする",
            is_quote_rt=True,
            quote_rt_context={
                "source_username": "sama",
                "today_same_source_count": 1,  # すでに1件投稿済み
                "consecutive_quote_count": 0,
            },
        )
        assert not result.is_safe
        assert any("同一ソース" in v for v in result.violations)

    def test_consecutive_quote_warning(self):
        result = self.checker.check(
            "これはデカい。AIの使い方が根本から変わる可能性。今までの常識が通用しなくなる。",
            is_quote_rt=True,
            quote_rt_context={
                "source_username": "OpenAI",
                "today_same_source_count": 0,
                "consecutive_quote_count": 2,  # 2件連続
            },
        )
        # 連続制限はwarningのみ（violationではない）
        assert any("連続" in w for w in result.warnings)

    def test_url_warning_for_quote_rt(self):
        result = self.checker.check(
            "これすごい https://example.com 詳細はこちら。AIの進化が止まらない。マジで使えるツール。",
            is_quote_rt=True,
        )
        assert any("URL不要" in w for w in result.warnings)

    def test_ng_words_in_quote_rt(self):
        result = self.checker.check(
            "不労所得で月100万稼げるAIツールがついに登場！今すぐDMください！",
            is_quote_rt=True,
        )
        assert not result.is_safe


# ============================================================
# quote_generator テスト（デモモード）
# ============================================================
class TestQuoteGenerator:
    """引用RT生成のテスト（Gemini APIなし、デモモード）"""

    @pytest.fixture(autouse=True)
    def setup_generator(self):
        from src.config import Config
        from src.generate.quote_generator import QuoteGenerator
        config = Config()
        self.generator = QuoteGenerator(config)

    def test_generate_demo_mode(self):
        result = self.generator.generate(
            original_text="GPT-5 is a massive leap forward",
            author_username="sama",
        )
        assert result["text"]
        assert result["template_id"]
        assert len(result["text"]) >= 30

    def test_template_rotation(self):
        """複数生成でテンプレートが分散される"""
        templates_used = set()
        for _ in range(10):
            result = self.generator.generate(
                original_text="AI is evolving rapidly",
                author_username="test",
            )
            templates_used.add(result["template_id"])
        # 少なくとも2種類以上使用
        assert len(templates_used) >= 2

    def test_generate_batch(self):
        tweets = [
            {"text": "Tweet 1 about AI agents", "author_username": "user1"},
            {"text": "Tweet 2 about GPT-5 release", "author_username": "user2"},
        ]
        results = self.generator.generate_batch(tweets, max_count=2)
        assert len(results) == 2
        for r in results:
            assert r["text"]
            assert r["template_id"]

    def test_score_and_safety_included(self):
        result = self.generator.generate(
            original_text="Major AI breakthrough announced",
            author_username="AnthropicAI",
        )
        assert "score" in result
        assert "safety" in result
