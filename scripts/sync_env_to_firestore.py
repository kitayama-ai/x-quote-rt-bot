#!/usr/bin/env python3
"""
.env の API キーを Firestore api_keys/{data_uid} に同期するワンショットスクリプト

Usage:
    python scripts/sync_env_to_firestore.py
    python scripts/sync_env_to_firestore.py --dry-run
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import dotenv_values
from src.firestore.firestore_client import FirestoreClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

# .env のキー名 → Firestore フィールド名
ENV_TO_FIRESTORE = {
    "X_API_KEY": "x_api_key",
    "X_API_SECRET": "x_api_secret",
    "TWITTER_BEARER_TOKEN": "x_bearer_token",
    "X_ACCOUNT_1_ACCESS_TOKEN": "x_access_token",
    "X_ACCOUNT_1_ACCESS_SECRET": "x_access_token_secret",
    "GEMINI_API_KEY": "gemini_api_key",
    "DISCORD_WEBHOOK_X_ACCOUNT_1": "discord_webhook_url",
}


def main():
    dry_run = "--dry-run" in sys.argv

    print("📦 .env → Firestore API キー同期")
    print(f"   ソース: {ENV_PATH}")

    # .env 読み込み
    env_vals = dotenv_values(ENV_PATH)

    # data_uid 検出
    fc = FirestoreClient()
    db = fc._get_db()

    docs = list(db.collection("api_keys").limit(1).stream())
    if not docs:
        print("❌ api_keys コレクションにドキュメントがありません")
        sys.exit(1)

    data_uid = docs[0].id
    print(f"   data_uid: {data_uid}")

    # マッピング
    updates = {}
    for env_key, fs_key in ENV_TO_FIRESTORE.items():
        val = env_vals.get(env_key, "")
        if val:
            updates[fs_key] = val
            masked = val[:6] + "..." + val[-4:] if len(val) > 14 else "***"
            print(f"   ✅ {env_key} → {fs_key} ({masked})")
        else:
            print(f"   ⏭️  {env_key} → (空のためスキップ)")

    if not updates:
        print("\n⚠️ 同期するキーがありません")
        return

    if dry_run:
        print(f"\n🔒 ドライラン: {len(updates)} 件のキーを書き込み予定")
        return

    # Firestore 書き込み（merge=True で既存フィールドを保持）
    db.collection("api_keys").document(data_uid).set(updates, merge=True)
    print(f"\n🎉 {len(updates)} 件のキーを Firestore に同期しました")


if __name__ == "__main__":
    main()
