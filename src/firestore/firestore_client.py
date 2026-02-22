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
                import re as _re
                # Base64パディング修正（改行・空白・パディング欠落を全て処理）
                b64str = self._credentials_base64
                # 1. 改行・空白・タブを全て除去
                b64str = _re.sub(r'\s+', '', b64str)
                # 2. 末尾の=をいったん除去して正規化
                b64str = b64str.rstrip('=')
                # 3. 正しいパディングを再付与
                missing_padding = len(b64str) % 4
                if missing_padding:
                    b64str += '=' * (4 - missing_padding)
                cred_json = base64.b64decode(b64str, validate=False).decode("utf-8")
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
        from google.cloud.firestore_v1.base_query import FieldFilter
        users = []
        query = db.collection("users").where(filter=FieldFilter("role", "==", "admin"))
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

    # ========================================
    # キュー決定（ダッシュボード → バックエンド同期）
    # ========================================

    def get_queue_decisions(self, uid: str = "") -> list[dict]:
        """
        ダッシュボードからのキュー操作（承認/スキップ）を取得

        Args:
            uid: ユーザーUID（指定時はそのユーザーのみ）

        Returns:
            [{"tweet_id": str, "action": str, "skip_reason": str, "decided_by": str, "uid": str, ...}]
        """
        db = self._get_db()
        decisions = []

        if uid:
            # 特定ユーザーのサブコレクションから取得
            for doc in db.collection("users").document(uid).collection("queue_decisions").stream():
                data = doc.to_dict()
                data["tweet_id"] = doc.id
                data["uid"] = uid
                decisions.append(data)
        else:
            # 全ユーザーをイテレート
            for user_doc in db.collection("users").stream():
                user_uid = user_doc.id
                for doc in db.collection("users").document(user_uid).collection("queue_decisions").stream():
                    data = doc.to_dict()
                    data["tweet_id"] = doc.id
                    data["uid"] = user_uid
                    decisions.append(data)

        return decisions

    def get_all_queue_decisions(self) -> dict[str, list[dict]]:
        """
        全ユーザーのキュー決定をUID別に取得

        Returns:
            {"uid1": [decisions...], "uid2": [decisions...]}
        """
        db = self._get_db()
        result: dict[str, list[dict]] = {}

        for user_doc in db.collection("users").stream():
            uid = user_doc.id
            decisions = []
            for doc in db.collection("users").document(uid).collection("queue_decisions").stream():
                data = doc.to_dict()
                data["tweet_id"] = doc.id
                data["uid"] = uid
                decisions.append(data)
            if decisions:
                result[uid] = decisions

        return result

    def mark_decisions_processed(self, tweet_ids: list[str], uid: str = "") -> int:
        """
        処理済みの決定をFirestoreから削除（バッチ処理）

        Args:
            tweet_ids: 処理済みのツイートIDリスト
            uid: ユーザーUID（サブコレクション用）

        Returns:
            削除件数
        """
        if not tweet_ids or not uid:
            return 0

        db = self._get_db()
        batch = db.batch()
        count = 0

        for tweet_id in tweet_ids:
            ref = db.collection("users").document(uid).collection("queue_decisions").document(tweet_id)
            batch.delete(ref)
            count += 1

            # Firestoreのバッチは最大500件
            if count % 500 == 0:
                batch.commit()
                batch = db.batch()

        if count % 500 != 0:
            batch.commit()

        return count

    # ========================================
    # 選定プリファレンス（ダッシュボード → バックエンド同期）
    # ========================================

    def get_selection_preferences(self, uid: str) -> dict | None:
        """
        ダッシュボードで設定された選定プリファレンスを取得

        Args:
            uid: Firebase Auth UID

        Returns:
            {
                "weekly_focus": "...",
                "focus_keywords": "AI agent, Claude",  # CSV形式
                "preferred_topics": "AI agents, coding AI",
                ...
            } or None
        """
        db = self._get_db()
        doc = db.collection("selection_preferences").document(uid).get()
        if doc.exists:
            data = doc.to_dict()
            # Firestore Timestamp をフィルタ（JSON非対応）
            return {
                k: v for k, v in data.items()
                if not hasattr(v, 'timestamp')  # Timestamp型を除外
            }
        return None

    # ========================================
    # 操作リクエスト（ダッシュボード → バックエンド実行）
    # ========================================

    def get_pending_operations(self, uid: str = "") -> list[dict]:
        """
        ダッシュボードから送信された未処理の操作リクエストを取得

        Args:
            uid: ユーザーUID（指定時はそのユーザーのみ）

        Returns:
            [{"id": "doc_id", "uid": "user_uid", "command": "collect", "status": "pending", ...}, ...]
        """
        db = self._get_db()
        from google.cloud.firestore_v1.base_query import FieldFilter
        results = []

        if uid:
            docs = (
                db.collection("users").document(uid).collection("operation_requests")
                .where(filter=FieldFilter("status", "==", "pending"))
                .order_by("requested_at")
                .limit(10)
                .stream()
            )
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id
                data["uid"] = uid
                results.append(data)
        else:
            # 全ユーザーをイテレート
            for user_doc in db.collection("users").stream():
                user_uid = user_doc.id
                try:
                    docs = (
                        db.collection("users").document(user_uid).collection("operation_requests")
                        .where(filter=FieldFilter("status", "==", "pending"))
                        .order_by("requested_at")
                        .limit(10)
                        .stream()
                    )
                    for doc in docs:
                        data = doc.to_dict()
                        data["id"] = doc.id
                        data["uid"] = user_uid
                        results.append(data)
                except Exception:
                    pass  # サブコレクションが無い場合はスキップ

        return results

    def get_all_pending_operations(self) -> dict[str, list[dict]]:
        """
        全ユーザーの未処理操作リクエストをUID別に取得

        Returns:
            {"uid1": [operations...], "uid2": [operations...]}
        """
        db = self._get_db()
        from google.cloud.firestore_v1.base_query import FieldFilter
        result: dict[str, list[dict]] = {}

        for user_doc in db.collection("users").stream():
            uid = user_doc.id
            try:
                docs = (
                    db.collection("users").document(uid).collection("operation_requests")
                    .where(filter=FieldFilter("status", "==", "pending"))
                    .order_by("requested_at")
                    .limit(10)
                    .stream()
                )
                ops = []
                for doc in docs:
                    data = doc.to_dict()
                    data["id"] = doc.id
                    data["uid"] = uid
                    ops.append(data)
                if ops:
                    result[uid] = ops
            except Exception:
                pass

        return result

    def update_operation_status(self, doc_id: str, status: str, result: str = "", uid: str = "") -> None:
        """
        操作リクエストのステータスを更新

        Args:
            doc_id: Firestoreドキュメント ID
            status: "running", "completed", "failed"
            result: 結果メッセージ（任意）
            uid: ユーザーUID（サブコレクション用）
        """
        db = self._get_db()
        import datetime
        if uid:
            db.collection("users").document(uid).collection("operation_requests").document(doc_id).update({
                "status": status,
                "result": result,
                "processed_at": datetime.datetime.now(datetime.timezone.utc),
            })
        else:
            # フォールバック: 旧形式
            db.collection("operation_requests").document(doc_id).update({
                "status": status,
                "result": result,
                "processed_at": datetime.datetime.now(datetime.timezone.utc),
            })
