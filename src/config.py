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
        return os.getenv("GEMINI_API_KEY", "")

    @property
    def gemini_model(self) -> str:
        return self._accounts_config["global"]["gemini_model"]

    # === X API ===

    @property
    def x_api_key(self) -> str:
        return os.getenv("X_API_KEY", "")

    @property
    def x_api_secret(self) -> str:
        return os.getenv("X_API_SECRET", "")

    @property
    def x_access_token(self) -> str:
        prefix = self._account["env_prefix"]
        return os.getenv(f"{prefix}_ACCESS_TOKEN", "")

    @property
    def x_access_secret(self) -> str:
        prefix = self._account["env_prefix"]
        return os.getenv(f"{prefix}_ACCESS_SECRET", "")

    # === Discord ===

    @property
    def discord_webhook_account(self) -> str:
        return os.getenv(f"DISCORD_WEBHOOK_{self._account['env_prefix']}", "")

    @property
    def discord_webhook_general(self) -> str:
        return os.getenv("DISCORD_WEBHOOK_GENERAL", "")

    @property
    def discord_webhook_metrics(self) -> str:
        return os.getenv("DISCORD_WEBHOOK_METRICS", "")

    @property
    def discord_webhook_safety(self) -> str:
        return os.getenv("DISCORD_WEBHOOK_SAFETY", "")

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
        return self._account["name"]

    @property
    def account_handle(self) -> str:
        return self._account["handle"]

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

    # === アクティブアカウント一覧 ===

    def get_active_accounts(self) -> list[dict]:
        return [a for a in self._accounts_config["accounts"] if a.get("active", True)]
