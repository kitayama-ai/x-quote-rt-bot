"""
X Auto Post System — X API v2 クライアント

tweepy を使って X API v2 経由でバズツイートを検索・取得する。
従量課金プラン ($0.005/読み取り) を前提とした実装。

環境変数:
    TWITTER_BEARER_TOKEN: X API v2 の Bearer Token
"""
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import tweepy

JST = ZoneInfo("Asia/Tokyo")

DEFAULT_MIN_LIKES = 500
DEFAULT_LANG = "en"
DEFAULT_MAX_RESULTS = 50

# tweepy が返すレスポンスを SocialData 互換 dict に変換するためのフィールド
TWEET_FIELDS = ["created_at", "public_metrics", "author_id", "lang", "text"]
USER_FIELDS = ["username", "name"]
EXPANSIONS = ["author_id"]


class XAPIError(Exception):
    """X API v2 エラー"""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"X API v2 error {status_code}: {message}")


class XAPIClient:
    """X API v2 クライアント (tweepy ラッパー)"""

    def __init__(self, bearer_token: str = ""):
        self.bearer_token = bearer_token or os.getenv("TWITTER_BEARER_TOKEN", "")
        if not self.bearer_token:
            raise ValueError(
                "TWITTER_BEARER_TOKEN が未設定です。\n"
                ".env に TWITTER_BEARER_TOKEN=your_token を追加してください。"
            )
        self.client = tweepy.Client(
            bearer_token=self.bearer_token,
            wait_on_rate_limit=True,
        )
        # ユーザー名キャッシュ (author_id -> {username, name})
        self._user_cache: dict[str, dict] = {}

    def search_tweets(
        self,
        query: str,
        max_results: int = DEFAULT_MAX_RESULTS,
        tweet_type: str = "Latest",
    ) -> list[dict]:
        """
        ツイートを検索 (search_recent_tweets — 過去7日間)

        Args:
            query: 検索クエリ (Twitter 検索構文)
            max_results: 最大取得件数
            tweet_type: "Latest" or "Top" (X API v2 では sort_order)

        Returns:
            SocialData 互換の dict リスト
        """
        sort_order = "recency" if tweet_type == "Latest" else "relevancy"

        # X API v2 は max_results 10-100 の範囲
        per_page = min(max_results, 100)

        try:
            response = self.client.search_recent_tweets(
                query=query,
                max_results=per_page,
                tweet_fields=TWEET_FIELDS,
                user_fields=USER_FIELDS,
                expansions=EXPANSIONS,
                sort_order=sort_order,
            )
        except tweepy.errors.TooManyRequests:
            raise XAPIError(429, "レート制限に達しました。しばらく待ってから再試行してください。")
        except tweepy.errors.Unauthorized:
            raise XAPIError(401, "Bearer Token が無効です。TWITTER_BEARER_TOKEN を確認してください。")
        except tweepy.errors.Forbidden as e:
            raise XAPIError(403, f"アクセスが拒否されました: {e}")
        except tweepy.errors.TweepyException as e:
            raise XAPIError(0, f"API エラー: {e}")

        if not response.data:
            return []

        # expansions からユーザー情報を取得してキャッシュ
        self._cache_users_from_includes(response)

        # SocialData 互換形式に変換
        tweets = []
        for tweet in response.data:
            tweets.append(self._to_compat_dict(tweet))

        return tweets[:max_results]

    def get_tweet(self, tweet_id: str) -> dict:
        """
        ツイートIDから詳細を取得

        Args:
            tweet_id: ツイートID

        Returns:
            SocialData 互換の dict
        """
        try:
            response = self.client.get_tweet(
                id=tweet_id,
                tweet_fields=TWEET_FIELDS,
                user_fields=USER_FIELDS,
                expansions=EXPANSIONS,
            )
        except tweepy.errors.TweepyException as e:
            raise XAPIError(0, f"ツイート取得エラー: {e}")

        if not response.data:
            raise XAPIError(404, f"ツイートが見つかりません: {tweet_id}")

        self._cache_users_from_includes(response)
        return self._to_compat_dict(response.data)

    def get_user_tweets(
        self,
        username: str,
        max_results: int = 20,
    ) -> list[dict]:
        """
        ユーザーの最新ツイートを取得

        Args:
            username: X のユーザー名 (@なし)
            max_results: 最大取得件数

        Returns:
            SocialData 互換の dict リスト
        """
        # まずユーザーIDを取得
        try:
            user_resp = self.client.get_user(username=username)
        except tweepy.errors.TweepyException as e:
            raise XAPIError(0, f"ユーザー取得エラー (@{username}): {e}")

        if not user_resp.data:
            raise XAPIError(404, f"ユーザーが見つかりません: @{username}")

        user_id = user_resp.data.id
        self._user_cache[str(user_id)] = {
            "username": user_resp.data.username,
            "name": user_resp.data.name or "",
        }

        per_page = min(max_results, 100)

        try:
            response = self.client.get_users_tweets(
                id=user_id,
                max_results=per_page,
                tweet_fields=TWEET_FIELDS,
                exclude=["retweets", "replies"],
            )
        except tweepy.errors.TweepyException as e:
            raise XAPIError(0, f"ツイート取得エラー (@{username}): {e}")

        if not response.data:
            return []

        tweets = []
        for tweet in response.data:
            tweets.append(self._to_compat_dict(tweet, fallback_username=username))

        return tweets[:max_results]

    def build_search_query(
        self,
        accounts: list[str] | None = None,
        keywords: list[str] | None = None,
        min_likes: int = DEFAULT_MIN_LIKES,
        lang: str = DEFAULT_LANG,
        exclude_replies: bool = True,
        exclude_retweets: bool = True,
    ) -> str:
        """
        検索クエリを組み立て (Twitter 検索構文 — X API v2 互換)

        Args:
            accounts: 監視対象アカウントのユーザー名リスト
            keywords: キーワードリスト
            min_likes: 最低いいね数
            lang: 言語コード
            exclude_replies: リプライを除外
            exclude_retweets: RT を除外

        Returns:
            検索クエリ文字列
        """
        parts = []

        if accounts:
            from_parts = [f"from:{u}" for u in accounts]
            parts.append(f"({' OR '.join(from_parts)})")

        if keywords and not accounts:
            kw_parts = [f'"{kw}"' if " " in kw else kw for kw in keywords]
            parts.append(f"({' OR '.join(kw_parts)})")

        # min_faves はBasicプラン以上でないと使えないため、
        # Python側でフィルタする（auto_collector._filter_tweets）
        # if min_likes > 0:
        #     parts.append(f"min_faves:{min_likes}")

        if lang:
            parts.append(f"lang:{lang}")

        if exclude_replies:
            parts.append("-is:reply")

        if exclude_retweets:
            parts.append("-is:retweet")

        return " ".join(parts)

    # ── internal helpers ──────────────────────────────────────────

    def _cache_users_from_includes(self, response) -> None:
        """レスポンスの includes.users をキャッシュに追加"""
        if hasattr(response, "includes") and response.includes:
            users = response.includes.get("users", [])
            for user in users:
                self._user_cache[str(user.id)] = {
                    "username": user.username,
                    "name": user.name or "",
                }

    def _to_compat_dict(self, tweet, fallback_username: str = "") -> dict:
        """
        tweepy.Tweet を SocialData 互換の dict に変換

        既存の tweet_parser.py の from_api_data() が期待するフォーマットに合わせる。
        """
        metrics = tweet.public_metrics or {}
        author_id = str(getattr(tweet, "author_id", ""))

        # ユーザー情報をキャッシュから取得
        user_info = self._user_cache.get(author_id, {})
        username = user_info.get("username", fallback_username)
        name = user_info.get("name", "")

        # created_at を文字列に変換 (SocialData 形式)
        created_at = getattr(tweet, "created_at", None)
        if isinstance(created_at, datetime):
            created_at_str = created_at.strftime("%a %b %d %H:%M:%S %z %Y")
        else:
            created_at_str = str(created_at) if created_at else ""

        return {
            "id": tweet.id,
            "id_str": str(tweet.id),
            "text": tweet.text or "",
            "full_text": tweet.text or "",
            "user": {
                "screen_name": username,
                "name": name,
            },
            "created_at": created_at_str,
            "favorite_count": metrics.get("like_count", 0),
            "retweet_count": metrics.get("retweet_count", 0),
            "reply_count": metrics.get("reply_count", 0),
            "quote_count": metrics.get("quote_count", 0),
            "bookmark_count": 0,  # X API v2 では取得不可
            "lang": getattr(tweet, "lang", "") or "",
            "in_reply_to_status_id": None,
            "retweeted_status": None,
        }
