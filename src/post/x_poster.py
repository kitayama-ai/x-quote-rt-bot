"""
X Auto Post System — X API投稿 (requests-oauthlib)

tweepy の POST /2/tweets が Pay Per Use プランで403になるため、
requests-oauthlib による OAuth 1.0a 直接実装に切り替え。
引用RT・通常投稿・削除に対応。
"""
import os
import requests
from requests_oauthlib import OAuth1Session

from src.config import Config


class XPoster:
    """X (Twitter) APIを使った投稿 (requests-oauthlib版)"""

    BASE_URL = "https://api.twitter.com/2"

    def __init__(self, config: Config):
        self.config = config
        self._session = None

    @property
    def session(self) -> OAuth1Session:
        """OAuth1Session (lazy init)"""
        if self._session is None:
            self._session = OAuth1Session(
                self.config.x_api_key,
                client_secret=self.config.x_api_secret,
                resource_owner_key=self.config.x_access_token,
                resource_owner_secret=self.config.x_access_secret,
            )
        return self._session

    def verify_credentials(self) -> dict:
        """
        アカウント確認（誤投稿防止）

        Returns:
            {"id": str, "name": str, "username": str}
        """
        # Bearer Token で /2/users/me は使えないため
        # OAuth1.0a で get_me 相当を確認する
        # → 投稿テストの代わりにアカウント情報を取得
        import tweepy
        client = tweepy.Client(
            consumer_key=self.config.x_api_key,
            consumer_secret=self.config.x_api_secret,
            access_token=self.config.x_access_token,
            access_token_secret=self.config.x_access_secret,
            wait_on_rate_limit=True
        )
        me = client.get_me()
        if not me or not me.data:
            raise RuntimeError("アカウント確認に失敗しました")

        return {
            "id": me.data.id,
            "name": me.data.name,
            "username": me.data.username
        }

    def post_tweet(
        self,
        text: str,
        media_ids: list[str] | None = None,
        quote_tweet_id: str | None = None,
        reply_to_id: str | None = None,
    ) -> dict:
        """
        テキストツイートを投稿（引用RT・リプライ対応）

        Args:
            text: 投稿テキスト (280字以内)
            media_ids: メディアID（任意）
            quote_tweet_id: 引用RT対象のツイートID（任意）
            reply_to_id: リプライ対象のツイートID（任意）

        Returns:
            {"id": str, "text": str}
        """
        payload: dict = {"text": text}

        if media_ids:
            payload["media"] = {"media_ids": media_ids}
        if quote_tweet_id:
            payload["quote_tweet_id"] = quote_tweet_id
        if reply_to_id:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}

        response = self.session.post(
            f"{self.BASE_URL}/tweets",
            json=payload,
        )

        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"投稿に失敗しました: {response.status_code} {response.json()}"
            )

        data = response.json().get("data", {})
        return {
            "id": data.get("id", ""),
            "text": data.get("text", text),
        }

    def delete_tweet(self, tweet_id: str) -> bool:
        """
        ツイートを削除

        Args:
            tweet_id: 削除するツイートID

        Returns:
            True if deleted
        """
        response = self.session.delete(f"{self.BASE_URL}/tweets/{tweet_id}")
        if response.status_code == 200:
            return response.json().get("data", {}).get("deleted", False)
        raise RuntimeError(
            f"削除に失敗しました: {response.status_code} {response.json()}"
        )

    def upload_media(self, file_path: str) -> str:
        """
        メディアをアップロード（v1.1 API使用）

        Args:
            file_path: メディアファイルのパス

        Returns:
            media_id (str)
        """
        import tweepy
        auth = tweepy.OAuth1UserHandler(
            consumer_key=self.config.x_api_key,
            consumer_secret=self.config.x_api_secret,
            access_token=self.config.x_access_token,
            access_token_secret=self.config.x_access_secret,
        )
        api = tweepy.API(auth, wait_on_rate_limit=True)
        media = api.media_upload(file_path)
        return str(media.media_id)

    def post_with_image(self, text: str, image_path: str) -> dict:
        """テキスト + 画像を投稿"""
        media_id = self.upload_media(image_path)
        return self.post_tweet(text, media_ids=[media_id])

    def get_recent_tweets(self, max_results: int = 10) -> list[dict]:
        """
        自分の最近のツイートを取得（重複チェック用）

        Returns:
            [{"id": str, "text": str, "created_at": datetime}]
        """
        import tweepy
        client = tweepy.Client(
            consumer_key=self.config.x_api_key,
            consumer_secret=self.config.x_api_secret,
            access_token=self.config.x_access_token,
            access_token_secret=self.config.x_access_secret,
            wait_on_rate_limit=True,
        )
        me = client.get_me()
        if not me or not me.data:
            return []

        tweets = client.get_users_tweets(
            me.data.id,
            max_results=max_results,
            tweet_fields=["created_at"],
        )

        if not tweets or not tweets.data:
            return []

        return [
            {
                "id": str(t.id),
                "text": t.text,
                "created_at": t.created_at,
            }
            for t in tweets.data
        ]

    def get_tweet_metrics(self, tweet_id: str) -> dict:
        """
        ツイートのエンゲージメントを取得

        Returns:
            {"likes": int, "retweets": int, "replies": int, ...}
        """
        import tweepy
        client = tweepy.Client(
            bearer_token=os.getenv("TWITTER_BEARER_TOKEN", ""),
            wait_on_rate_limit=True,
        )
        tweet = client.get_tweet(
            tweet_id,
            tweet_fields=["public_metrics", "created_at"],
        )

        if not tweet or not tweet.data:
            return {}

        metrics = tweet.data.public_metrics or {}
        return {
            "likes": metrics.get("like_count", 0),
            "retweets": metrics.get("retweet_count", 0),
            "replies": metrics.get("reply_count", 0),
            "impressions": metrics.get("impression_count", 0),
            "quotes": metrics.get("quote_count", 0),
            "bookmarks": metrics.get("bookmark_count", 0),
            "created_at": str(tweet.data.created_at) if tweet.data.created_at else "",
        }
