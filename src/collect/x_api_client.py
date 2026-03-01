"""
X Auto Post System — X API v2 クライアント

requests を使って X API v2 経由でバズツイートを検索・取得する。
従量課金プラン ($0.005/読み取り) を前提とした実装。

環境変数:
    TWITTER_BEARER_TOKEN: X API v2 の Bearer Token
"""
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

JST = ZoneInfo("Asia/Tokyo")

DEFAULT_MIN_LIKES = 500
DEFAULT_LANG = "en"
DEFAULT_MAX_RESULTS = 50

# X API v2 JSON レスポンスを SocialData 互換 dict に変換するためのフィールド
TWEET_FIELDS = ["created_at", "public_metrics", "author_id", "lang", "text"]
USER_FIELDS = ["username", "name"]
EXPANSIONS = ["author_id"]


class XAPIError(Exception):
    """X API v2 エラー"""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"X API v2 error {status_code}: {message}")


class XAPIClient:
    """X API v2 クライアント (requests ダイレクト実装)"""

    def __init__(self, bearer_token: str = ""):
        self.bearer_token = bearer_token or os.getenv("TWITTER_BEARER_TOKEN", "")
        if not self.bearer_token:
            raise ValueError(
                "TWITTER_BEARER_TOKEN が未設定です。\n"
                ".env に TWITTER_BEARER_TOKEN=your_token を追加してください。"
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

        base_url = "https://api.twitter.com/2/tweets/search/recent"
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        params = {
            "query": query,
            "max_results": per_page,
            "tweet.fields": ",".join(TWEET_FIELDS),
            "user.fields": ",".join(USER_FIELDS),
            "expansions": ",".join(EXPANSIONS),
            "sort_order": sort_order,
        }

        try:
            resp = requests.get(base_url, headers=headers, params=params, timeout=30)
        except requests.RequestException as e:
            raise XAPIError(0, f"ネットワークエラー: {e}")

        if resp.status_code == 429:
            raise XAPIError(429, "レート制限に達しました。しばらく待ってから再試行してください。")
        elif resp.status_code == 401:
            raise XAPIError(401, "Bearer Token が無効です。TWITTER_BEARER_TOKEN を確認してください。")
        elif resp.status_code == 403:
            # Cloudflare ブロック（HTML）と API 正規 403（JSON）を区別
            body = resp.text[:300]
            if "<html" in body.lower() or "Just a moment" in body:
                raise XAPIError(403, f"Cloudflare にブロックされました（GitHub Actions IP）。body={body[:150]}")
            raise XAPIError(403, f"アクセスが拒否されました。body={body[:200]}")
        elif resp.status_code != 200:
            raise XAPIError(resp.status_code, f"API エラー: {resp.text[:200]}")

        try:
            data = resp.json()
        except ValueError as e:
            raise XAPIError(0, f"JSON パースエラー: {e}")

        tweets_data = data.get("data", [])
        if not tweets_data:
            return []

        # includes からユーザー情報を取得してキャッシュ
        includes = data.get("includes", {})
        users = includes.get("users", [])
        for user in users:
            self._user_cache[str(user.get("id"))] = {
                "username": user.get("username", ""),
                "name": user.get("name", ""),
            }

        # SocialData 互換形式に変換
        tweets = []
        for tweet_obj in tweets_data:
            tweets.append(self._to_compat_dict_from_json(tweet_obj))

        return tweets[:max_results]

    def get_tweet(self, tweet_id: str) -> dict:
        """
        ツイートIDから詳細を取得

        Args:
            tweet_id: ツイートID

        Returns:
            SocialData 互換の dict
        """
        base_url = f"https://api.twitter.com/2/tweets/{tweet_id}"
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        params = {
            "tweet.fields": ",".join(TWEET_FIELDS),
            "user.fields": ",".join(USER_FIELDS),
            "expansions": ",".join(EXPANSIONS),
        }

        try:
            resp = requests.get(base_url, headers=headers, params=params, timeout=30)
        except requests.RequestException as e:
            raise XAPIError(0, f"ネットワークエラー: {e}")

        if resp.status_code == 404:
            raise XAPIError(404, f"ツイートが見つかりません: {tweet_id}")
        elif resp.status_code != 200:
            raise XAPIError(resp.status_code, f"API エラー: {resp.text[:200]}")

        try:
            data = resp.json()
        except ValueError as e:
            raise XAPIError(0, f"JSON パースエラー: {e}")

        tweet_obj = data.get("data")
        if not tweet_obj:
            raise XAPIError(404, f"ツイートが見つかりません: {tweet_id}")

        # includes からユーザー情報を取得してキャッシュ
        includes = data.get("includes", {})
        users = includes.get("users", [])
        for user in users:
            self._user_cache[str(user.get("id"))] = {
                "username": user.get("username", ""),
                "name": user.get("name", ""),
            }

        return self._to_compat_dict_from_json(tweet_obj)

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
        base_url = f"https://api.twitter.com/2/users/by/username/{username}"
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        params = {
            "user.fields": ",".join(USER_FIELDS),
        }

        try:
            resp = requests.get(base_url, headers=headers, params=params, timeout=30)
        except requests.RequestException as e:
            raise XAPIError(0, f"ネットワークエラー: {e}")

        if resp.status_code == 404:
            raise XAPIError(404, f"ユーザーが見つかりません: @{username}")
        elif resp.status_code != 200:
            raise XAPIError(resp.status_code, f"API エラー: {resp.text[:200]}")

        try:
            data = resp.json()
        except ValueError as e:
            raise XAPIError(0, f"JSON パースエラー: {e}")

        user_obj = data.get("data")
        if not user_obj:
            raise XAPIError(404, f"ユーザーが見つかりません: @{username}")

        user_id = user_obj.get("id")
        self._user_cache[str(user_id)] = {
            "username": user_obj.get("username", ""),
            "name": user_obj.get("name", ""),
        }

        # ユーザーのツイートを取得
        per_page = min(max_results, 100)
        base_url = f"https://api.twitter.com/2/users/{user_id}/tweets"
        params = {
            "max_results": per_page,
            "tweet.fields": ",".join(TWEET_FIELDS),
            "exclude": "retweets,replies",
        }

        try:
            resp = requests.get(base_url, headers=headers, params=params, timeout=30)
        except requests.RequestException as e:
            raise XAPIError(0, f"ネットワークエラー: {e}")

        if resp.status_code != 200:
            raise XAPIError(resp.status_code, f"ツイート取得エラー: {resp.text[:200]}")

        try:
            data = resp.json()
        except ValueError as e:
            raise XAPIError(0, f"JSON パースエラー: {e}")

        tweets_data = data.get("data", [])
        if not tweets_data:
            return []

        tweets = []
        for tweet_obj in tweets_data:
            tweets.append(self._to_compat_dict_from_json(tweet_obj, fallback_username=username))

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

    def _to_compat_dict_from_json(self, tweet_obj: dict, fallback_username: str = "") -> dict:
        """
        X API v2 JSON レスポンスを SocialData 互換の dict に変換

        既存の tweet_parser.py の from_api_data() が期待するフォーマットに合わせる。
        """
        tweet_id = tweet_obj.get("id", "")
        text = tweet_obj.get("text", "")
        metrics = tweet_obj.get("public_metrics", {})
        author_id = str(tweet_obj.get("author_id", ""))
        created_at_str = tweet_obj.get("created_at", "")
        lang = tweet_obj.get("lang", "")

        # ユーザー情報をキャッシュから取得
        user_info = self._user_cache.get(author_id, {})
        username = user_info.get("username", fallback_username)
        name = user_info.get("name", "")

        # created_at は ISO 8601 形式から SocialData 形式に変換
        # X API: "2026-02-20T02:14:30.000Z" -> SocialData: "Thu Feb 20 02:14:30 +0000 2026"
        if created_at_str:
            try:
                dt = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                created_at_str = dt.strftime("%a %b %d %H:%M:%S %z %Y")
            except (ValueError, TypeError):
                pass  # パースできない場合はそのまま使用

        return {
            "id": tweet_id,
            "id_str": str(tweet_id),
            "text": text,
            "full_text": text,
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
            "lang": lang,
            "in_reply_to_status_id": None,
            "retweeted_status": None,
        }
