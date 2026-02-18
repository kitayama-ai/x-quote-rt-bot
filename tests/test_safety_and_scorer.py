"""
テスト — 安全チェッカー & スコアラー
"""
import pytest
from src.post.safety_checker import SafetyChecker
from src.analyze.scorer import PostScorer


# ========================================
# SafetyChecker Tests
# ========================================

@pytest.fixture
def safety_rules():
    return {
        "ng_words": {
            "info_scam": ["不労所得", "月100万", "誰でもすぐ"],
            "company": ["cyan", "シアン", "ISAI"],
            "personal": ["北田", "kitada"],
            "ai_smell": ["素晴らしい", "いかがでしたか"]
        },
        "content_rules": {
            "max_hashtags": 3,
            "max_links": 1,
            "min_length": 40,
            "max_length": 280,
            "max_emoji": 3
        },
        "quality_rules": {
            "duplicate_threshold": 0.8
        },
        "posting_rules": {
            "posting_interval_min_minutes": 240
        }
    }


@pytest.fixture
def checker(safety_rules):
    return SafetyChecker(safety_rules)


class TestSafetyChecker:
    def test_safe_post(self, checker):
        """正常な投稿は通過する"""
        text = "ぶっちゃけ、AIで副業を自動化したら\n1日3時間の作業が30分になった。\n\nマジでやばい。みんなどうしてる？"
        result = checker.check(text)
        assert result.is_safe

    def test_ng_word_info_scam(self, checker):
        """情報商材系NGワードを検出"""
        text = "不労所得で月100万円稼げる方法を教えます！ぜひ活用してみてください！"
        result = checker.check(text)
        assert not result.is_safe
        assert any("NGワード" in v for v in result.violations)

    def test_ng_word_company(self, checker):
        """会社名NGワードを検出"""
        text = "cyanの新しいプロジェクトがマジでやばい。AI使ってるんだけど、結果出てる。"
        result = checker.check(text)
        assert not result.is_safe

    def test_ng_word_personal(self, checker):
        """個人情報NGワードを検出"""
        text = "北田さんと話してて思ったんだけど、AI副業って本当にすごいよね。マジで変わった。"
        result = checker.check(text)
        assert not result.is_safe

    def test_too_short(self, checker):
        """文字数不足を検出"""
        text = "マジでやばい。"
        result = checker.check(text)
        assert not result.is_safe
        assert any("文字数不足" in v for v in result.violations)

    def test_too_long(self, checker):
        """文字数超過を検出"""
        text = "あ" * 300
        result = checker.check(text)
        assert not result.is_safe
        assert any("文字数超過" in v for v in result.violations)

    def test_too_many_hashtags(self, checker):
        """ハッシュタグ過多を検出"""
        text = "ぶっちゃけ、AIで副業を自動化したらマジでやばい。みんなもやってみて！ #AI #副業 #自動化 #ChatGPT"
        result = checker.check(text)
        assert not result.is_safe

    def test_duplicate_detection(self, checker):
        """重複投稿を検出"""
        text = "ぶっちゃけ、AIで副業を自動化したら1日3時間の作業が30分になった。マジでやばい。"
        past = ["ぶっちゃけ、AIで副業を自動化したら1日3時間の作業が30分になった。マジでやばい。"]
        result = checker.check(text, past_posts=past)
        assert not result.is_safe
        assert any("類似度" in v for v in result.violations)

    def test_posting_interval(self, checker):
        """投稿間隔不足を検出"""
        text = "ぶっちゃけ、AIで副業を自動化したら1日3時間の作業が30分になった。マジでやばい。"
        result = checker.check(text, last_post_minutes_ago=60)
        assert not result.is_safe
        assert any("投稿間隔" in v for v in result.violations)


# ========================================
# PostScorer Tests
# ========================================

@pytest.fixture
def scorer():
    return PostScorer()


class TestPostScorer:
    def test_high_score_post(self, scorer):
        """高品質な投稿は高スコアになる"""
        text = (
            "ぶっちゃけ、AIで投稿を自動化したら\n"
            "3時間の作業が30分になった。\n\n"
            "Claude Codeで仕組みを作る。\n"
            "マジでこれ一択。\n\n"
            "やってる人いる？"
        )
        result = scorer.score(text)
        assert result.total >= 6
        assert result.rank in ("S", "A")

    def test_low_score_ai_smell(self, scorer):
        """AI感のある投稿は低スコアになる"""
        text = (
            "AIツールの活用について解説します。\n"
            "素晴らしい革新的なツールが登場しました。\n"
            "ぜひ活用してみてください。\n"
            "いかがでしたか？"
        )
        result = scorer.score(text)
        assert result.humanity < 2  # 人間味スコアが低い

    def test_hook_detection(self, scorer):
        """強フックパターンを検出"""
        text = "マジで言ってる。\nAI副業で月5万円。\n結論出た。"
        result = scorer.score(text)
        assert result.hook == 2  # 強フック

    def test_specificity_with_numbers(self, scorer):
        """具体的数字がある投稿は具体性スコアが高い"""
        text = "3時間を30分にした方法。\n月3万円の副収入。\nAI×GASで仕組み化。\nみんなどうしてる？"
        result = scorer.score(text)
        assert result.specificity >= 1

    def test_url_penalty(self, scorer):
        """URL含有でペナルティ"""
        text = "ぶっちゃけマジでやばいツール見つけた。\nhttps://example.com\nこれ使ってみて。みんなもやってみて。"
        result = scorer.score(text)
        assert result.penalty < 0

    def test_format_score(self, scorer):
        """スコアフォーマットが正しく出力される"""
        text = "正直、もう限界だった。\n3時間の作業が30分になった。\nこれマジでやばい。"
        result = scorer.score(text)
        formatted = scorer.format_score(result)
        assert "スコア" in formatted
        assert "/8" in formatted
