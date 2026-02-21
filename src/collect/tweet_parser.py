"""
X Auto Post System — ツイートURL解析・データ正規化

ツイートURLからIDを抽出し、ツイートデータを標準フォーマットに変換する。
"""
import re
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


@dataclass
class ParsedTweet:
    """解析済みツイートデータ"""
    tweet_id: str
    author_username: str = ""
    author_name: str = ""
    text: str = ""
    lang: str = ""
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    quotes: int = 0
    bookmarks: int = 0
    url: str = ""
    collected_at: str = ""
    source: str = "manual"  # "manual" | "x_api_v2" | "socialdata"
    tags: list[str] = field(default_factory=list)
    memo: str = ""  # 収集時のメモ
    # プリファレンスマッチ情報（選定PDCAで使用）
    preference_match_score: float = 0.0
    matched_topics: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tweet_id": self.tweet_id,
            "author_username": self.author_username,
            "author_name": self.author_name,
            "text": self.text,
            "lang": self.lang,
            "likes": self.likes,
            "retweets": self.retweets,
            "replies": self.replies,
            "quotes": self.quotes,
            "bookmarks": self.bookmarks,
            "url": self.url,
            "collected_at": self.collected_at,
            "source": self.source,
            "tags": self.tags,
            "memo": self.memo,
            "preference_match_score": self.preference_match_score,
            "matched_topics": self.matched_topics,
            "matched_keywords": self.matched_keywords,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ParsedTweet":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class TweetParser:
    """ツイートURLの解析とデータ正規化"""

    # X/Twitter URLパターン
    URL_PATTERNS = [
        # https://x.com/username/status/1234567890
        re.compile(r"https?://(?:x|twitter)\.com/(\w+)/status/(\d+)"),
        # https://mobile.twitter.com/username/status/1234567890
        re.compile(r"https?://mobile\.(?:x|twitter)\.com/(\w+)/status/(\d+)"),
        # https://vxtwitter.com/username/status/1234567890 (embed用)
        re.compile(r"https?://(?:vx|fx)twitter\.com/(\w+)/status/(\d+)"),
    ]

    @classmethod
    def parse_url(cls, url: str) -> tuple[str, str] | None:
        """
        ツイートURLからユーザー名とツイートIDを抽出

        Args:
            url: ツイートURL

        Returns:
            (username, tweet_id) or None
        """
        url = url.strip()
        # クエリパラメータを除去
        url_clean = url.split("?")[0]

        for pattern in cls.URL_PATTERNS:
            match = pattern.match(url_clean)
            if match:
                return match.group(1), match.group(2)

        return None

    @classmethod
    def extract_tweet_id(cls, url: str) -> str | None:
        """URLからツイートIDのみ抽出"""
        result = cls.parse_url(url)
        return result[1] if result else None

    @classmethod
    def build_url(cls, username: str, tweet_id: str) -> str:
        """ツイートURLを構築"""
        return f"https://x.com/{username}/status/{tweet_id}"

    @classmethod
    def from_url(cls, url: str, text: str = "", memo: str = "") -> ParsedTweet:
        """
        URLから手動収集用のParsedTweetを生成

        Args:
            url: ツイートURL
            text: ツイートのテキスト（手動コピペ）
            memo: 収集時のメモ
        """
        parsed = cls.parse_url(url)
        if not parsed:
            raise ValueError(f"無効なツイートURL: {url}")

        username, tweet_id = parsed
        return ParsedTweet(
            tweet_id=tweet_id,
            author_username=username,
            text=text,
            url=cls.build_url(username, tweet_id),
            collected_at=datetime.now(JST).isoformat(),
            source="manual",
            memo=memo,
        )

    @classmethod
    def from_api_data(cls, data: dict, source: str = "socialdata") -> ParsedTweet:
        """
        API取得データからParsedTweetを生成（パターンB用）

        Args:
            data: API応答のツイートデータ
            source: データソース名
        """
        # 各APIの形式に対応するため柔軟にマッピング
        tweet_id = str(data.get("id", data.get("tweet_id", "")))
        author = data.get("user", data.get("author", {}))

        return ParsedTweet(
            tweet_id=tweet_id,
            author_username=author.get("screen_name", author.get("username", "")),
            author_name=author.get("name", ""),
            text=data.get("text", data.get("full_text", "")),
            lang=data.get("lang", ""),
            likes=data.get("favorite_count", data.get("like_count", 0)),
            retweets=data.get("retweet_count", 0),
            replies=data.get("reply_count", 0),
            quotes=data.get("quote_count", 0),
            bookmarks=data.get("bookmark_count", 0),
            url=TweetParser.build_url(
                author.get("screen_name", author.get("username", "unknown")),
                tweet_id
            ),
            collected_at=datetime.now(JST).isoformat(),
            source=source,
        )


def is_valid_tweet_url(url: str) -> bool:
    """ツイートURLの妥当性をチェック"""
    return TweetParser.parse_url(url) is not None
