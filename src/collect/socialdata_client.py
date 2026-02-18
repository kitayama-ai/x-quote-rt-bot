"""
X Auto Post System — SocialData APIクライアント（パターンB）

SocialData API (https://socialdata.tools) を使って
海外AIバズツイートを自動収集する。

環境変数:
    SOCIALDATA_API_KEY: SocialData APIキー
"""
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

JST = ZoneInfo("Asia/Tokyo")

# SocialData API ベースURL
BASE_URL = "https://api.socialdata.tools"

# デフォルトの検索パラメータ
DEFAULT_MIN_LIKES = 500
DEFAULT_LANG = "en"
DEFAULT_MAX_RESULTS = 50


class SocialDataError(Exception):
    """SocialData API エラー"""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"SocialData API error {status_code}: {message}")


class SocialDataClient:
    """SocialData API クライアント"""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.getenv("SOCIALDATA_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "SOCIALDATA_API_KEY が未設定です。"
                ".env に SOCIALDATA_API_KEY=your_key を追加してください。"
            )
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        })

    def search_tweets(
        self,
        query: str,
        max_results: int = DEFAULT_MAX_RESULTS,
        tweet_type: str = "Latest",
    ) -> list[dict]:
        """
        ツイートを検索

        Args:
            query: 検索クエリ（Twitter検索構文）
            max_results: 最大取得件数
            tweet_type: "Latest" or "Top"

        Returns:
            ツイートオブジェクトのリスト
        """
        url = f"{BASE_URL}/twitter/search"
        params = {
            "query": query,
            "type": tweet_type,
        }

        all_tweets = []
        cursor = None

        while len(all_tweets) < max_results:
            if cursor:
                params["cursor"] = cursor

            resp = self._request("GET", url, params=params)
            data = resp.json()

            tweets = data.get("tweets", [])
            if not tweets:
                break

            all_tweets.extend(tweets)
            cursor = data.get("next_cursor")
            if not cursor:
                break

            # レート制限対策: リクエスト間に少し待つ
            time.sleep(0.5)

        return all_tweets[:max_results]

    def get_tweet(self, tweet_id: str) -> dict:
        """
        ツイートIDから詳細を取得

        Args:
            tweet_id: ツイートID

        Returns:
            ツイートオブジェクト
        """
        url = f"{BASE_URL}/twitter/statuses/show"
        params = {"id": tweet_id}
        resp = self._request("GET", url, params=params)
        return resp.json()

    def get_user_tweets(
        self,
        user_id: str,
        max_results: int = 20,
    ) -> list[dict]:
        """
        ユーザーの最新ツイートを取得

        Args:
            user_id: ユーザーID
            max_results: 最大取得件数

        Returns:
            ツイートオブジェクトのリスト
        """
        url = f"{BASE_URL}/twitter/user/tweets"
        params = {
            "user_id": user_id,
        }
        resp = self._request("GET", url, params=params)
        data = resp.json()
        tweets = data.get("tweets", [])
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
        検索クエリを組み立てる

        Args:
            accounts: 監視対象アカウントのユーザー名リスト
            keywords: キーワードリスト
            min_likes: 最低いいね数
            lang: 言語コード
            exclude_replies: リプライを除外
            exclude_retweets: RTを除外

        Returns:
            Twitter検索クエリ文字列
        """
        parts = []

        # アカウント指定（ORで結合）
        if accounts:
            from_parts = [f"from:{u}" for u in accounts]
            parts.append(f"({' OR '.join(from_parts)})")

        # キーワード（ORで結合）
        if keywords and not accounts:
            kw_parts = [f'"{kw}"' if " " in kw else kw for kw in keywords]
            parts.append(f"({' OR '.join(kw_parts)})")

        # フィルタ
        if min_likes > 0:
            parts.append(f"min_faves:{min_likes}")

        if lang:
            parts.append(f"lang:{lang}")

        if exclude_replies:
            parts.append("-filter:replies")

        if exclude_retweets:
            parts.append("-filter:retweets")

        return " ".join(parts)

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """HTTPリクエストを実行（エラーハンドリング付き）"""
        try:
            resp = self.session.request(method, url, timeout=30, **kwargs)
        except requests.RequestException as e:
            raise SocialDataError(0, f"接続エラー: {e}")

        if resp.status_code == 429:
            raise SocialDataError(429, "レート制限に達しました。しばらく待ってから再試行してください。")

        if resp.status_code == 401:
            raise SocialDataError(401, "APIキーが無効です。SOCIALDATA_API_KEY を確認してください。")

        if resp.status_code >= 400:
            msg = resp.text[:200] if resp.text else "不明なエラー"
            raise SocialDataError(resp.status_code, msg)

        return resp
