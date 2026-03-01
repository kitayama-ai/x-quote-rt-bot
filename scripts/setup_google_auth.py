#!/usr/bin/env python3
"""
Google認証セットアップスクリプト

Firestore に x_accounts と account_access を作成し、
Google OAuth ログインでダッシュボードにアクセスできるようにする。

Usage:
    python scripts/setup_google_auth.py \
        --admin-email yamato.kitada@cyan-inc.net \
        --account-id account_1 \
        --x-handle "@NinjaGuild_Japan"

    # data_uid を手動指定する場合:
    python scripts/setup_google_auth.py \
        --admin-email yamato.kitada@cyan-inc.net \
        --data-uid "abc123..." \
        --account-id account_1 \
        --x-handle "@NinjaGuild_Japan"
"""
import argparse
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.firestore.firestore_client import FirestoreClient


def detect_data_uid(fc: FirestoreClient) -> str:
    """Firestore の既存コレクションから data_uid (ドキュメントID) を自動検出"""
    db = fc._get_db()

    # dashboard_data コレクションから検出
    print("  🔍 dashboard_data コレクションを検索中...")
    docs = list(db.collection("dashboard_data").limit(5).stream())
    if docs:
        for doc in docs:
            print(f"     発見: {doc.id}")
        if len(docs) == 1:
            return docs[0].id
        # 複数ある場合はリストを表示
        print(f"\n  ⚠️ 複数の dashboard_data ドキュメントが見つかりました:")
        for i, doc in enumerate(docs):
            data = doc.to_dict()
            updated = data.get("updated_at", "?")
            print(f"     [{i + 1}] {doc.id} (更新: {updated})")
        choice = input(f"\n  使用するドキュメントの番号を入力 [1-{len(docs)}]: ").strip()
        idx = int(choice) - 1
        if 0 <= idx < len(docs):
            return docs[idx].id
        print("  ❌ 無効な選択")
        sys.exit(1)

    # api_keys コレクションから検出
    print("  🔍 api_keys コレクションを検索中...")
    docs = list(db.collection("api_keys").limit(5).stream())
    if docs:
        for doc in docs:
            print(f"     発見: {doc.id}")
        if len(docs) == 1:
            return docs[0].id

    # users コレクションから検出
    print("  🔍 users コレクションを検索中...")
    docs = list(db.collection("users").limit(5).stream())
    if docs:
        for doc in docs:
            data = doc.to_dict()
            print(f"     発見: {doc.id} (@{data.get('twitterUsername', '?')})")
        if len(docs) == 1:
            return docs[0].id

    print("  ❌ 既存データが見つかりませんでした。--data-uid オプションで手動指定してください。")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Google認証セットアップ")
    parser.add_argument("--admin-email", required=True, help="管理者の Google メールアドレス")
    parser.add_argument("--data-uid", default="", help="既存の Firebase UID（空欄で自動検出）")
    parser.add_argument("--account-id", default="account_1", help="アカウントID（デフォルト: account_1）")
    parser.add_argument("--x-handle", default="", help="X アカウントのハンドル名（例: @NinjaGuild_Japan）")
    parser.add_argument("--display-name", default="", help="アカウント表示名")
    parser.add_argument("--dry-run", action="store_true", help="実行せずに確認のみ")
    args = parser.parse_args()

    print("╔══════════════════════════════════════════════╗")
    print("║  Google認証セットアップ                       ║")
    print("╚══════════════════════════════════════════════╝")

    fc = FirestoreClient()
    db = fc._get_db()

    # data_uid の検出
    data_uid = args.data_uid
    if not data_uid:
        print("\n📡 data_uid を自動検出中...")
        data_uid = detect_data_uid(fc)
    print(f"\n✅ data_uid: {data_uid}")

    # 設定確認
    admin_email = args.admin_email.strip().lower()
    account_id = args.account_id
    x_handle = args.x_handle or "(未設定)"
    display_name = args.display_name or x_handle.lstrip("@") or account_id

    print(f"\n📋 セットアップ内容:")
    print(f"  Admin メール:  {admin_email}")
    print(f"  Account ID:    {account_id}")
    print(f"  X ハンドル:    {x_handle}")
    print(f"  表示名:        {display_name}")
    print(f"  Data UID:      {data_uid}")

    if args.dry_run:
        print("\n🔒 ドライラン: 実際の書き込みはスキップされました")
        return

    # 既存チェック
    existing = db.collection("x_accounts").document(account_id).get()
    if existing.exists:
        print(f"\n⚠️ x_accounts/{account_id} は既に存在します")
        data = existing.to_dict()
        print(f"   既存の allowed_emails: {data.get('allowed_emails', [])}")
        overwrite = input("   上書きしますか？ [y/N]: ").strip().lower()
        if overwrite != "y":
            print("   スキップしました")
            return

    # Firestore バッチ書き込み
    print("\n📝 Firestore に書き込み中...")
    from google.cloud.firestore_v1 import SERVER_TIMESTAMP

    batch = db.batch()

    # 1. x_accounts/{accountId}
    account_ref = db.collection("x_accounts").document(account_id)
    batch.set(account_ref, {
        "x_handle": x_handle,
        "display_name": display_name,
        "data_uid": data_uid,
        "allowed_emails": [admin_email],
        "member_roles": {admin_email: "admin"},
        "created_at": SERVER_TIMESTAMP,
        "updated_at": SERVER_TIMESTAMP,
    })
    print(f"  ✅ x_accounts/{account_id}")

    # 2. account_access/{email}
    access_ref = db.collection("account_access").document(admin_email)
    batch.set(access_ref, {
        "data_uid": data_uid,
        "account_id": account_id,
        "role": "admin",
        "granted_at": SERVER_TIMESTAMP,
        "granted_by": "setup_script",
    })
    print(f"  ✅ account_access/{admin_email}")

    batch.commit()

    print(f"\n🎉 セットアップ完了！")
    print(f"\n次のステップ:")
    print(f"  1. Firebase Console > Authentication > Sign-in method で Google を有効化")
    print(f"  2. ダッシュボード (index.html) をデプロイ")
    print(f"  3. {admin_email} で Google ログインしてテスト")


if __name__ == "__main__":
    main()
