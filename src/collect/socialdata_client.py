"""
X Auto Post System — SocialData API クライアント

SocialData API (https://socialdata.tools) 経由でバズツイートを検索・取得する。
Twitter v1.1 互換のレスポンスを返すため、既存の TweetParser がそのまま利用可能。

料金: $0.0002 / ツイート（$0.20 / 1,000ツイート）
認証: Authorization: Bearer <API_KEY>
BANリスク: ゼロ（SocialData側インフラで取得するため自アカウントは無関係）

環境変数:
    SOCIALDATA_API_KEY: SocialData API キー
"""
from __future__ import annotations

import os
import logging
from urllib.parse import quote as url_quote

import requests

logger = logging.getLogger(__name__)

# SocialData API 定数
_BASE_URL = "https://api.socialdata.tools"
_SEARCH_ENDPOINT = f"{_BASE_URL}/twitter/search"
_DEFAULT_TIMEOUT = 30


class SocialDataError(Exception):
    """SocialData API エラー"""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"SocialData API error {status_code}: {message}")


class SocialDataClient:
    """
    SocialData API クライアント

    Twitter v1.1 互換のレスポンスを返すため、既存の TweetParser.from_api_data()
    で ParsedTweet に変換可能。

    Usage:
        client = SocialDataClient(api_key="YOUR_KEY")
        tweets = client.search("AI agent min_faves:500 -filter:replies", search_type="Top")
        for tweet in tweets:
            print(tweet["favorite_count"], tweet["full_text"])
    """

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key or os.getenv("SOCIALDATA_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "SOCIALDATA_API_KEY が未設定です。\n"
                "ダッシュボードまたは環境変数に SocialData API キーを設定してください。"
            )

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        *,
        search_type: str = "Top",
        max_results: int = 20,
    ) -> list[dict]:
        """
        ツイートを検索して Twitter v1.1 互換の dict リストを返す。

        Args:
            query: Twitter 検索構文のクエリ文字列。
                   例: "AI agent min_faves:500 lang:en -filter:replies"
            search_type: "Top"（人気順）または "Latest"（最新順）。
                         バズツイート収集では "Top" を推奨。
            max_results: 最大取得件数。1ページ20件のため、20の倍数が効率的。
                         ページネーションで複数ページを自動取得する。

        Returns:
            Twitter v1.1 互換フォーマットの dict リスト。
            各 dict は以下のキーを含む:
                - id_str, full_text, favorite_count, retweet_count,
                  reply_count, quote_count, views_count, bookmark_count,
                  user.screen_name, user.followers_count, user.verified,
                  lang, tweet_created_at, in_reply_to_status_id_str

        Raises:
            SocialDataError: API リクエストが失敗した場合。
        """
        all_tweets: list[dict] = []
        cursor: str | None = None
        pages_fetched = 0
        max_pages = max(max_results // 20, 1)

        while len(all_tweets) < max_results and pages_fetched < max_pages:
            tweets, cursor = self._fetch_page(query, search_type, cursor)
            if not tweets:
                break

            all_tweets.extend(tweets)
            pages_fetched += 1

            if cursor is None:
                break

        return all_tweets[:max_results]

    def build_search_query(
        self,
        *,
        keywords: list[str] | None = None,
        min_faves: int = 0,
        min_retweets: int = 0,
        lang: str = "en",
        exclude_replies: bool = True,
        exclude_retweets: bool = True,
    ) -> str:
        """
        検索クエリを組み立てる。

        SocialData は Twitter の検索構文をそのまま使えるため、
        min_faves / min_retweets による API レベルのフィルタが可能。

        Args:
            keywords: キーワードリスト（OR 結合）。
            min_faves: 最低いいね数。0 の場合はフィルタなし。
            min_retweets: 最低RT数。0 の場合はフィルタなし。
            lang: 言語コード。空文字でフィルタなし。
            exclude_replies: リプライを除外するか。
            exclude_retweets: RT を除外するか。

        Returns:
            検索クエリ文字列。
        """
        parts: list[str] = []

        if keywords:
            kw_parts = [f'"{kw}"' if " " in kw else kw for kw in keywords]
            parts.append(f"({' OR '.join(kw_parts)})")

        if min_faves > 0:
            parts.append(f"min_faves:{min_faves}")

        if min_retweets > 0:
            parts.append(f"min_retweets:{min_retweets}")

        if lang:
            parts.append(f"lang:{lang}")

        if exclude_replies:
            parts.append("-filter:replies")

        if exclude_retweets:
            parts.append("-filter:retweets")

        return " ".join(parts)

    # ──────────────────────────────────────────────────────────────
    # Internal
    # ──────────────────────────────────────────────────────────────

    def _fetch_page(
        self,
        query: str,
        search_type: str,
        cursor: str | None,
    ) -> tuple[list[dict], str | None]:
        """
        1 ページ分のツイートを取得する。

        Returns:
            (tweets, next_cursor) のタプル。
            next_cursor が None の場合、次ページなし。
        """
        params: dict[str, str] = {
            "query": query,
            "type": search_type,
        }
        if cursor:
            params["cursor"] = cursor

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

        try:
            resp = requests.get(
                _SEARCH_ENDPOINT,
                headers=headers,
                params=params,
                timeout=_DEFAULT_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise SocialDataError(0, f"ネットワークエラー: {exc}") from exc

        if resp.status_code == 402:
            raise SocialDataError(402, "クレジット不足です。SocialData ダッシュボードでチャージしてください。")

        if resp.status_code == 422:
            raise SocialDataError(422, f"クエリが不正です: {resp.text[:200]}")

        if resp.status_code == 500:
            raise SocialDataError(500, "SocialData 内部エラー。しばらく待ってから再試行してください。")

        if resp.status_code != 200:
            raise SocialDataError(resp.status_code, f"API エラー: {resp.text[:200]}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise SocialDataError(0, f"JSON パースエラー: {exc}") from exc

        tweets = data.get("tweets", [])
        next_cursor = data.get("next_cursor")

        return tweets, next_cursor
