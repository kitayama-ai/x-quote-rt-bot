"""
X Auto Post System — X API投稿 (tweepy)

ai-tweet-collector/XPoster.gs のOAuth 1.0a実装をPython版に移植。
"""
import tweepy
from src.config import Config


class XPoster:
    """X (Twitter) APIを使った投稿"""

    def __init__(self, config: Config):
        self.config = config
        self._client = None
        self._api = None

    @property
    def client(self) -> tweepy.Client:
        """tweepy v2 Client (lazy init)"""
        if self._client is None:
            self._client = tweepy.Client(
                consumer_key=self.config.x_api_key,
                consumer_secret=self.config.x_api_secret,
                access_token=self.config.x_access_token,
                access_token_secret=self.config.x_access_secret,
                wait_on_rate_limit=True
            )
        return self._client

    @property
    def api(self) -> tweepy.API:
        """tweepy v1.1 API (メディアアップロード用, lazy init)"""
        if self._api is None:
            auth = tweepy.OAuth1UserHandler(
                consumer_key=self.config.x_api_key,
                consumer_secret=self.config.x_api_secret,
                access_token=self.config.x_access_token,
                access_token_secret=self.config.x_access_secret
            )
            self._api = tweepy.API(auth, wait_on_rate_limit=True)
        return self._api

    def verify_credentials(self) -> dict:
        """
        アカウント確認（誤投稿防止）

        Returns:
            {"id": str, "name": str, "username": str}
        """
        me = self.client.get_me()
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
        kwargs = {"text": text}
        if media_ids:
            kwargs["media_ids"] = media_ids
        if quote_tweet_id:
            kwargs["quote_tweet_id"] = quote_tweet_id
        if reply_to_id:
            kwargs["in_reply_to_tweet_id"] = reply_to_id

        response = self.client.create_tweet(**kwargs)
        if not response or not response.data:
            raise RuntimeError(f"投稿に失敗しました: {response}")

        return {
            "id": response.data["id"],
            "text": response.data.get("text", text)
        }

    def upload_media(self, file_path: str) -> str:
        """
        メディアをアップロード

        Args:
            file_path: メディアファイルのパス

        Returns:
            media_id (str)
        """
        media = self.api.media_upload(file_path)
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
        me = self.client.get_me()
        if not me or not me.data:
            return []

        tweets = self.client.get_users_tweets(
            me.data.id,
            max_results=max_results,
            tweet_fields=["created_at"]
        )

        if not tweets or not tweets.data:
            return []

        return [
            {
                "id": str(t.id),
                "text": t.text,
                "created_at": t.created_at
            }
            for t in tweets.data
        ]

    def get_tweet_metrics(self, tweet_id: str) -> dict:
        """
        ツイートのエンゲージメントを取得

        Returns:
            {"likes": int, "retweets": int, "replies": int, "impressions": int, ...}
        """
        tweet = self.client.get_tweet(
            tweet_id,
            tweet_fields=["public_metrics", "created_at"]
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
            "created_at": str(tweet.data.created_at) if tweet.data.created_at else ""
        }
