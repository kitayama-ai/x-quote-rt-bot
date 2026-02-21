"""
X Auto Post System — Firestore クライアント

Firebase Firestore からユーザー別APIキーを取得する。
マルチテナント運用: 各ユーザーが自身のAPIキーをダッシュボードで登録し、
バックエンド（GitHub Actions等）がFirestoreから取得して使用する。
"""
import json
import os
from pathlib import Path

from src.config import PROJECT_ROOT


class FirestoreClient:
    """Firestore からユーザーデータ・APIキーを取得"""

    def __init__(self, credentials_path: str = "", project_id: str = ""):
        """
        Args:
            credentials_path: Firebase Admin SDKのサービスアカウントJSONパス
            project_id: Firebase プロジェクトID
        """
        self.project_id = project_id or os.getenv("FIREBASE_PROJECT_ID", "isai-11f7b")
        self._db = None
        self._credentials_path = credentials_path or os.getenv(
            "FIREBASE_CREDENTIALS_PATH",
            str(PROJECT_ROOT / "config" / "firebase-service-account.json")
        )

        # Base64 エンコードされた credentials 対応（GitHub Actions用）
        self._credentials_base64 = os.getenv("FIREBASE_CREDENTIALS_BASE64", "")

    def _get_db(self):
        """遅延初期化で Firestore クライアントを取得"""
        if self._db is not None:
            return self._db

        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
        except ImportError:
            raise ImportError(
                "firebase-admin パッケージが必要です。\n"
                "pip install firebase-admin"
            )

        # 既にアプリが初期化済みならそれを使う
        try:
            app = firebase_admin.get_app()
        except ValueError:
            # 新規初期化
            if self._credentials_base64:
                import base64
                import tempfile
                cred_json = base64.b64decode(self._credentials_base64).decode("utf-8")
                cred_dict = json.loads(cred_json)
                cred = credentials.Certificate(cred_dict)
            elif Path(self._credentials_path).exists():
                cred = credentials.Certificate(self._credentials_path)
            else:
                # Application Default Credentials（Cloud環境用）
                cred = credentials.ApplicationDefault()

            app = firebase_admin.initialize_app(cred, {
                "projectId": self.project_id,
            })

        self._db = firestore.client()
        return self._db

    # ========================================
    # ユーザー管理
    # ========================================

    def get_user(self, uid: str) -> dict | None:
        """
        ユーザー情報を取得

        Args:
            uid: Firebase Auth UID

        Returns:
            {"email", "displayName", "role", "provider", ...} or None
        """
        db = self._get_db()
        doc = db.collection("users").document(uid).get()
        if doc.exists:
            return doc.to_dict()
        return None

    def get_all_users(self) -> list[dict]:
        """全ユーザーを取得"""
        db = self._get_db()
        users = []
        for doc in db.collection("users").stream():
            user = doc.to_dict()
            user["uid"] = doc.id
            users.append(user)
        return users

    def get_admin_users(self) -> list[dict]:
        """adminロールのユーザーのみ取得"""
        db = self._get_db()
        users = []
        query = db.collection("users").where("role", "==", "admin")
        for doc in query.stream():
            user = doc.to_dict()
            user["uid"] = doc.id
            users.append(user)
        return users

    # ========================================
    # APIキー管理
    # ========================================

    def get_api_keys(self, uid: str) -> dict | None:
        """
        ユーザーのAPIキーを取得

        Args:
            uid: Firebase Auth UID

        Returns:
            {
                "socialdata_api_key": "...",
                "openai_api_key": "...",
                "x_bearer_token": "...",
                "x_api_key": "...",
                "x_api_secret": "...",
                "x_access_token": "...",
                "x_access_token_secret": "...",
            } or None
        """
        db = self._get_db()
        doc = db.collection("api_keys").document(uid).get()
        if doc.exists:
            data = doc.to_dict()
            # メタデータを除外して返す
            return {k: v for k, v in data.items() if k not in ("uid", "updatedAt")}
        return None

    def get_user_x_credentials(self, uid: str) -> dict | None:
        """
        X API 用の認証情報をまとめて取得

        Returns:
            {
                "api_key": "...",
                "api_secret": "...",
                "bearer_token": "...",
                "access_token": "...",
                "access_token_secret": "...",
            } or None
        """
        keys = self.get_api_keys(uid)
        if not keys:
            return None

        return {
            "api_key": keys.get("x_api_key", ""),
            "api_secret": keys.get("x_api_secret", ""),
            "bearer_token": keys.get("x_bearer_token", ""),
            "access_token": keys.get("x_access_token", ""),
            "access_token_secret": keys.get("x_access_token_secret", ""),
        }

    def get_user_socialdata_key(self, uid: str) -> str:
        """SocialData APIキーを取得"""
        keys = self.get_api_keys(uid)
        if keys:
            return keys.get("socialdata_api_key", "")
        return ""

    def get_user_openai_key(self, uid: str) -> str:
        """OpenAI APIキーを取得"""
        keys = self.get_api_keys(uid)
        if keys:
            return keys.get("openai_api_key", "")
        return ""

    # ========================================
    # ダッシュボードデータ書き込み
    # ========================================

    def update_dashboard_data(self, uid: str, data: dict) -> None:
        """
        ダッシュボード用データをFirestoreに保存

        Args:
            uid: ユーザーUID
            data: ダッシュボード表示用データ
        """
        db = self._get_db()
        from google.cloud.firestore import SERVER_TIMESTAMP
        data["updatedAt"] = SERVER_TIMESTAMP
        data["uid"] = uid
        db.collection("dashboard_data").document(uid).set(data, merge=True)

    def get_dashboard_data(self, uid: str) -> dict | None:
        """ユーザーのダッシュボードデータを取得"""
        db = self._get_db()
        doc = db.collection("dashboard_data").document(uid).get()
        if doc.exists:
            return doc.to_dict()
        return None

    # ========================================
    # ペルソナ・文体データ
    # ========================================

    def save_persona_profile(self, uid: str, profile: dict) -> None:
        """
        Xアカウントの文体分析結果を保存

        Args:
            uid: ユーザーUID
            profile: 文体分析結果
        """
        db = self._get_db()
        from google.cloud.firestore import SERVER_TIMESTAMP
        profile["updatedAt"] = SERVER_TIMESTAMP
        profile["uid"] = uid
        db.collection("persona_profiles").document(uid).set(profile, merge=True)

    def get_persona_profile(self, uid: str) -> dict | None:
        """ペルソナプロファイルを取得"""
        db = self._get_db()
        doc = db.collection("persona_profiles").document(uid).get()
        if doc.exists:
            return doc.to_dict()
        return None
