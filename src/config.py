"""
X Auto Post System — 設定管理
"""
import json
import os
from pathlib import Path
from dotenv import load_dotenv

# プロジェクトルート
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Config:
    """全設定を統合管理するクラス"""

    def __init__(self, account_id: str = "account_1"):
        self.account_id = account_id
        self._accounts_config = self._load_json("config/accounts.json")
        self._safety_rules = self._load_json("config/safety_rules.json")
        self._account = self._get_account(account_id)
        self._firestore_keys: dict = {}
        self._load_firestore_keys()

    def _load_firestore_keys(self):
        """DATA_UID が設定されていれば Firestore から API キーを読み込む

        Firestore の api_keys/{DATA_UID} に保存されたキーを取得し、
        未設定の環境変数に注入する。既存の環境変数は上書きしない。
        """
        data_uid = os.getenv("DATA_UID") or os.getenv("FIREBASE_UID", "")
        if not data_uid:
            return

        try:
            from src.firestore.firestore_client import FirestoreClient
            fc = FirestoreClient()
            keys = fc.get_api_keys(data_uid)
            if not keys:
                return
            self._firestore_keys = keys

            # Firestore キー名 → 環境変数名のマッピング
            env_map = {
                "gemini_api_key": "GEMINI_API_KEY",
                "x_api_key": "X_API_KEY",
                "x_api_secret": "X_API_SECRET",
                "x_access_token": f"{self._account['env_prefix']}_ACCESS_TOKEN",
                "x_access_token_secret": f"{self._account['env_prefix']}_ACCESS_SECRET",
                "x_bearer_token": "TWITTER_BEARER_TOKEN",
                "discord_webhook_url": f"DISCORD_WEBHOOK_{self._account['env_prefix']}",
            }

            injected = 0
            for fs_key, env_key in env_map.items():
                val = keys.get(fs_key, "")
                if val and not os.getenv(env_key):
                    os.environ[env_key] = val
                    injected += 1

            if injected:
                print(f"🔑 Firestore API キー読み込み: {injected}項目 (DATA_UID: {data_uid[:8]}...)")
        except Exception as e:
            print(f"⚠️ Firestore API キー読み込みスキップ: {e}")

    # === ファクトリ ===

    @staticmethod
    def _load_json(relative_path: str) -> dict:
        path = PROJECT_ROOT / relative_path
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _get_account(self, account_id: str) -> dict:
        for acc in self._accounts_config["accounts"]:
            if acc["id"] == account_id:
                return acc
        raise ValueError(f"Account '{account_id}' not found in accounts.json")

    # === Gemini ===

    @property
    def gemini_api_key(self) -> str:
        return os.getenv("GEMINI_API_KEY", "") or self._firestore_keys.get("gemini_api_key", "")

    @property
    def gemini_model(self) -> str:
        return self._accounts_config["global"]["gemini_model"]

    # === X API ===

    @property
    def x_api_key(self) -> str:
        return os.getenv("X_API_KEY", "") or self._firestore_keys.get("x_api_key", "")

    @property
    def x_api_secret(self) -> str:
        return os.getenv("X_API_SECRET", "") or self._firestore_keys.get("x_api_secret", "")

    @property
    def x_access_token(self) -> str:
        prefix = self._account["env_prefix"]
        return os.getenv(f"{prefix}_ACCESS_TOKEN", "") or self._firestore_keys.get("x_access_token", "")

    @property
    def x_access_secret(self) -> str:
        prefix = self._account["env_prefix"]
        return os.getenv(f"{prefix}_ACCESS_SECRET", "") or self._firestore_keys.get("x_access_token_secret", "")

    # === Discord ===

    @property
    def discord_webhook_account(self) -> str:
        return os.getenv(f"DISCORD_WEBHOOK_{self._account['env_prefix']}", "") or self._firestore_keys.get("discord_webhook_url", "")

    @property
    def discord_webhook_general(self) -> str:
        return os.getenv("DISCORD_WEBHOOK_GENERAL", "")

    @property
    def discord_webhook_metrics(self) -> str:
        return os.getenv("DISCORD_WEBHOOK_METRICS", "")

    @property
    def discord_webhook_safety(self) -> str:
        return os.getenv("DISCORD_WEBHOOK_SAFETY", "")

    # === Firebase / Firestore ===

    @property
    def firebase_project_id(self) -> str:
        return os.getenv("FIREBASE_PROJECT_ID", "isai-11f7b")

    @property
    def firebase_credentials_path(self) -> str:
        return os.getenv(
            "FIREBASE_CREDENTIALS_PATH",
            str(PROJECT_ROOT / "config" / "firebase-service-account.json")
        )

    @property
    def firebase_credentials_base64(self) -> str:
        return os.getenv("FIREBASE_CREDENTIALS_BASE64", "")

    # === Google Sheets ===

    @property
    def spreadsheet_id(self) -> str:
        return os.getenv("SPREADSHEET_ID", "")

    @property
    def google_credentials_base64(self) -> str:
        return os.getenv("GOOGLE_CREDENTIALS_BASE64", "")

    # === アカウント情報 ===

    @property
    def account_name(self) -> str:
        """環境変数 X_ACCOUNT_NAME が設定されていれば優先（マルチユーザー対応）"""
        override = os.getenv("X_ACCOUNT_NAME", "")
        return override if override else self._account["name"]

    @property
    def account_handle(self) -> str:
        """環境変数 X_ACCOUNT_HANDLE が設定されていれば優先（マルチユーザー対応）"""
        override = os.getenv("X_ACCOUNT_HANDLE", "")
        return override if override else self._account["handle"]

    @property
    def account_theme(self) -> str:
        return self._account["theme"]

    @property
    def schedule(self) -> dict:
        return self._account["schedule"]

    @property
    def posting_rules(self) -> dict:
        return self._account["posting_rules"]

    # === 安全ルール ===

    @property
    def safety_rules(self) -> dict:
        return self._safety_rules

    @property
    def ng_words(self) -> list[str]:
        """全カテゴリのNGワードをフラット化"""
        words = []
        for category_words in self._safety_rules["ng_words"].values():
            words.extend(category_words)
        return words

    # === パス ===

    @property
    def master_data_path(self) -> Path:
        return PROJECT_ROOT / self._account["master_data"]

    @property
    def prompt_template_path(self) -> Path:
        return PROJECT_ROOT / self._account["prompt_template"]

    # === 動作モード ===

    @property
    def mode(self) -> str:
        return os.getenv("MODE", self._accounts_config["global"]["mode"])

    @property
    def auto_post_min_score(self) -> int:
        return int(os.getenv(
            "AUTO_POST_MIN_SCORE",
            self._accounts_config["global"]["auto_post_min_score"]
        ))

    # === マスターデータ読み込み ===

    def load_master_data(self) -> str:
        with open(self.master_data_path, "r", encoding="utf-8") as f:
            return f.read()

    def load_prompt_template(self) -> str:
        with open(self.prompt_template_path, "r", encoding="utf-8") as f:
            return f.read()

    # === SocialData API (deprecated — X API v2 に移行済み) ===

    @property
    def socialdata_api_key(self) -> str:
        return os.getenv("SOCIALDATA_API_KEY", "")

    # === ペルソナプロファイル ===

    @property
    def persona_profile_path(self) -> Path:
        """アカウント別ペルソナプロファイル保存先"""
        return PROJECT_ROOT / "data" / "persona" / f"{self.account_id}_persona.json"

    def load_persona_profile(self) -> dict | None:
        """保存済みペルソナプロファイルを読み込む"""
        path = self.persona_profile_path
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    # === アクティブアカウント一覧 ===

    def get_active_accounts(self) -> list[dict]:
        return [a for a in self._accounts_config["accounts"] if a.get("active", True)]
