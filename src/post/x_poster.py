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
        self._validate_credentials()

    def _validate_credentials(self):
        """認証情報が空でないことを確認（起動時チェック）"""
        missing = []
        if not self.config.x_api_key:
            missing.append("X_API_KEY")
        if not self.config.x_api_secret:
            missing.append("X_API_SECRET")
        if not self.config.x_access_token:
            missing.append(f"{self.config.account_id.upper().replace('ACCOUNT_', 'X_ACCOUNT_')}_ACCESS_TOKEN")
        if not self.config.x_access_secret:
            missing.append(f"{self.config.account_id.upper().replace('ACCOUNT_', 'X_ACCOUNT_')}_ACCESS_SECRET")
        if missing:
            raise RuntimeError(
                f"X API認証情報が未設定です: {', '.join(missing)}\n"
                "GitHub Secrets または .env を確認してください。"
            )

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
        アカウント確認（OAuth1Session版 — tweepy不要）
        GET /2/users/me でアカウントを確認する。
        X API Freeプランでは 401/403 になる場合があるため、
        呼び出し元で適切にハンドリングすること。

        Returns:
            {"id": str, "name": str, "username": str}

        Raises:
            RuntimeError: 認証失敗時
        """
        resp = self.session.get(f"{self.BASE_URL}/users/me")

        if resp.status_code == 200:
            data = resp.json().get("data", {})
            username = data.get("username", "")
            result = {
                "id": str(data.get("id", "")),
                "name": data.get("name", ""),
                "username": username,
            }
            expected_handle = self.config.account_handle.lstrip("@").lower()
            actual_handle = username.lower()
            if expected_handle and actual_handle != expected_handle:
                print(
                    f"  ℹ️ 認証アカウント: @{username}"
                    f"（設定上のデフォルト: @{expected_handle}）"
                )
            else:
                print(f"  ✅ 認証アカウント: @{username}")
            return result
        else:
            raise RuntimeError(
                f"アカウント確認に失敗しました: {resp.status_code} {resp.text[:300]}"
            )

    def post_tweet(
        self,
        text: str,
        media_ids: list[str] | None = None,
        quote_tweet_id: str | None = None,
        reply_to_id: str | None = None,
        quote_url: str | None = None,
    ) -> dict:
        """
        テキストツイートを投稿（引用RT・リプライ対応）

        quote_tweet_id で403「引用RT制限」が返った場合、
        quote_url が指定されていれば自動的にURL埋め込み方式にフォールバック。
        Cloudflare ブロック時は最大3回リトライ。

        Args:
            text: 投稿テキスト (280字以内)
            media_ids: メディアID（任意）
            quote_tweet_id: 引用RT対象のツイートID（任意）
            reply_to_id: リプライ対象のツイートID（任意）
            quote_url: フォールバック用の元ツイートURL（任意）

        Returns:
            {"id": str, "text": str}
        """
        import time as _time

        payload: dict = {"text": text}

        if media_ids:
            payload["media"] = {"media_ids": media_ids}
        if quote_tweet_id:
            payload["quote_tweet_id"] = quote_tweet_id
        if reply_to_id:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}

        last_error = None
        for attempt in range(3):
            if attempt > 0:
                wait = 5 * (2 ** attempt)  # 10s, 20s
                print(f"  ⏳ リトライ {attempt + 1}/3（{wait}秒待機）...")
                _time.sleep(wait)
                # セッションをリセット（Cloudflare対策）
                self._session = None

            response = self.session.post(
                f"{self.BASE_URL}/tweets",
                json=payload,
            )

            # 成功
            if response.status_code in (200, 201):
                try:
                    data = response.json().get("data", {})
                except (ValueError, KeyError):
                    raise RuntimeError(
                        f"レスポンスのJSONパースに失敗: {response.status_code} {response.text[:300]}"
                    )
                return {
                    "id": data.get("id", ""),
                    "text": data.get("text", text),
                }

            # JSONレスポンスか確認
            try:
                error_body = response.json()
            except (ValueError, KeyError):
                error_body = response.text[:300]

            # 403「引用RT制限」→ URL埋め込みフォールバック
            if (response.status_code == 403
                    and isinstance(error_body, dict)
                    and "Quoting" in error_body.get("detail", "")):
                if quote_url and quote_tweet_id:
                    print(f"    ↪ 引用RT制限 → URL埋め込み方式にフォールバック")
                    fallback_text = f"{text}\n{quote_url}"
                    fallback_payload = {"text": fallback_text}
                    if media_ids:
                        fallback_payload["media"] = {"media_ids": media_ids}
                    _time.sleep(3)
                    self._session = None
                    fb_resp = self.session.post(
                        f"{self.BASE_URL}/tweets", json=fallback_payload,
                    )
                    if fb_resp.status_code in (200, 201):
                        try:
                            fb_data = fb_resp.json().get("data", {})
                        except (ValueError, KeyError):
                            raise RuntimeError(
                                f"フォールバック応答のJSONパース失敗: {fb_resp.text[:300]}"
                            )
                        return {
                            "id": fb_data.get("id", ""),
                            "text": fb_data.get("text", fallback_text),
                        }
                    raise RuntimeError(
                        f"フォールバック投稿も失敗: {fb_resp.status_code} {fb_resp.text[:300]}"
                    )
                # quote_url未指定 or フォールバック不可
                raise RuntimeError(
                    f"投稿に失敗しました: {response.status_code} {error_body}"
                )

            # その他の403（認証エラー等）はリトライしない
            if response.status_code == 403 and isinstance(error_body, dict):
                raise RuntimeError(
                    f"投稿に失敗しました: {response.status_code} {error_body}"
                )

            # Cloudflareブロック（HTML応答）やその他のエラーはリトライ
            last_error = f"投稿に失敗しました: {response.status_code} {error_body}"
            print(f"  ⚠️ 投稿エラー（attempt {attempt + 1}）: {response.status_code}")

        raise RuntimeError(last_error)

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
        メディアをアップロード（v1.1 API — requests-oauthlib版）

        Args:
            file_path: メディアファイルのパス

        Returns:
            media_id (str)
        """
        upload_url = "https://upload.twitter.com/1.1/media/upload.json"
        with open(file_path, "rb") as f:
            resp = self.session.post(upload_url, files={"media": f})
        if resp.status_code not in (200, 201, 202):
            raise RuntimeError(
                f"メディアアップロード失敗: {resp.status_code} {resp.text[:300]}"
            )
        return str(resp.json().get("media_id_string", ""))

    def post_with_image(self, text: str, image_path: str) -> dict:
        """テキスト + 画像を投稿"""
        media_id = self.upload_media(image_path)
        return self.post_tweet(text, media_ids=[media_id])

    def get_recent_tweets(self, max_results: int = 10) -> list[dict]:
        """
        自分の最近のツイートを取得（重複チェック用 — requests-oauthlib版）

        X API Freeプランでは GET /2/users/me が制限されるため、
        401/403 の場合は空リストを返して処理を続行する。

        Returns:
            [{"id": str, "text": str, "created_at": str}]
        """
        try:
            # 1. 自分のユーザーID取得
            me_resp = self.session.get(f"{self.BASE_URL}/users/me")
            if me_resp.status_code != 200:
                print(f"  ⚠️ get_recent_tweets: GET /users/me → {me_resp.status_code}")
                return []
            user_id = me_resp.json().get("data", {}).get("id", "")
            if not user_id:
                return []

            # 2. ツイート取得
            params = {
                "max_results": min(max_results, 100),
                "tweet.fields": "created_at,text",
            }
            tweets_resp = self.session.get(
                f"{self.BASE_URL}/users/{user_id}/tweets", params=params
            )
            if tweets_resp.status_code != 200:
                print(f"  ⚠️ get_recent_tweets: GET /users/{{id}}/tweets → {tweets_resp.status_code}")
                return []

            tweets = tweets_resp.json().get("data", [])
            return [
                {
                    "id": t.get("id", ""),
                    "text": t.get("text", ""),
                    "created_at": t.get("created_at", ""),
                }
                for t in tweets
            ]
        except Exception as e:
            print(f"  ⚠️ get_recent_tweets: {e}")
            return []

    def get_tweet_metrics(self, tweet_id: str) -> dict:
        """
        ツイートのエンゲージメントを取得（requests版 — tweepy不要）

        Returns:
            {"likes": int, "retweets": int, "replies": int, ...}
        """
        bearer = os.getenv("TWITTER_BEARER_TOKEN", "")
        if not bearer:
            print("  ⚠️ get_tweet_metrics: TWITTER_BEARER_TOKEN 未設定")
            return {}

        headers = {"Authorization": f"Bearer {bearer}"}
        params = {"tweet.fields": "public_metrics,created_at"}
        try:
            resp = requests.get(
                f"{self.BASE_URL}/tweets/{tweet_id}",
                headers=headers, params=params, timeout=30,
            )
            if resp.status_code != 200:
                print(f"  ⚠️ get_tweet_metrics: {resp.status_code}")
                return {}

            data = resp.json().get("data", {})
            metrics = data.get("public_metrics", {})
            return {
                "likes": metrics.get("like_count", 0),
                "retweets": metrics.get("retweet_count", 0),
                "replies": metrics.get("reply_count", 0),
                "impressions": metrics.get("impression_count", 0),
                "quotes": metrics.get("quote_count", 0),
                "bookmarks": metrics.get("bookmark_count", 0),
                "created_at": data.get("created_at", ""),
            }
        except Exception as e:
            print(f"  ⚠️ get_tweet_metrics: {e}")
            return {}
