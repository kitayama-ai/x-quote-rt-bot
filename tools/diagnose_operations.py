#!/usr/bin/env python3
"""
操作リクエスト処理の診断スクリプト

Firestoreの状態を確認し、操作リクエストが拾われない原因を特定する。
"""
import os
import sys
import json

def main():
    print("=" * 60)
    print("🔍 操作リクエスト診断ツール")
    print("=" * 60)

    # 1. 環境変数チェック
    print("\n--- 1. 環境変数チェック ---")
    env_vars = {
        "FIREBASE_CREDENTIALS_BASE64": bool(os.getenv("FIREBASE_CREDENTIALS_BASE64")),
        "FIREBASE_UID": os.getenv("FIREBASE_UID", "(未設定)"),
        "X_API_KEY": bool(os.getenv("X_API_KEY")),
        "X_API_SECRET": bool(os.getenv("X_API_SECRET")),
        "X_ACCOUNT_1_ACCESS_TOKEN": bool(os.getenv("X_ACCOUNT_1_ACCESS_TOKEN")),
        "X_ACCOUNT_1_ACCESS_SECRET": bool(os.getenv("X_ACCOUNT_1_ACCESS_SECRET")),
        "TWITTER_BEARER_TOKEN": bool(os.getenv("TWITTER_BEARER_TOKEN")),
        "GEMINI_API_KEY": bool(os.getenv("GEMINI_API_KEY")),
    }
    for k, v in env_vars.items():
        status = "✅" if v and v is not False else "❌"
        display = v if isinstance(v, str) else ("設定済み" if v else "未設定")
        print(f"  {status} {k}: {display}")

    # 2. Firebase初期化
    print("\n--- 2. Firebase初期化 ---")
    try:
        from src.firestore.firestore_client import FirestoreClient
        fc = FirestoreClient()
        db = fc._get_db()
        print("  ✅ Firestore接続成功")
    except Exception as e:
        print(f"  ❌ Firestore接続失敗: {e}")
        return

    # 3. usersコレクション確認
    print("\n--- 3. usersコレクション確認 ---")
    try:
        users = list(db.collection("users").stream())
        print(f"  📊 usersドキュメント数: {len(users)}")
        for u in users:
            data = u.to_dict() or {}
            print(f"    - {u.id}: {json.dumps({k: str(v)[:50] for k, v in data.items()}, ensure_ascii=False)}")
    except Exception as e:
        print(f"  ❌ usersコレクション読み取り失敗: {e}")

    # 4. FIREBASE_UIDで直接取得
    firebase_uid = os.getenv("FIREBASE_UID", "")
    print(f"\n--- 4. FIREBASE_UID直接取得 (uid={firebase_uid[:12]}...) ---")
    if firebase_uid:
        try:
            # ユーザードキュメント存在確認
            user_doc = db.collection("users").document(firebase_uid).get()
            print(f"  📄 users/{firebase_uid[:12]}... ドキュメント存在: {user_doc.exists}")
            if user_doc.exists:
                print(f"    データ: {json.dumps(user_doc.to_dict() or {}, ensure_ascii=False, default=str)[:200]}")

            # サブコレクション確認
            ops = list(
                db.collection("users").document(firebase_uid)
                .collection("operation_requests")
                .stream()
            )
            print(f"  📋 operation_requests数（全件）: {len(ops)}")
            for op in ops[-5:]:  # 最新5件
                d = op.to_dict()
                print(f"    - [{d.get('status', '?')}] {d.get('command', '?')} "
                      f"by {d.get('requested_by', '?')} "
                      f"at {d.get('requested_at', '?')}")

            # pending のみ
            from google.cloud.firestore_v1.base_query import FieldFilter
            pending_ops = list(
                db.collection("users").document(firebase_uid)
                .collection("operation_requests")
                .where(filter=FieldFilter("status", "==", "pending"))
                .stream()
            )
            print(f"  ⏳ pending数: {len(pending_ops)}")
            for op in pending_ops:
                d = op.to_dict()
                print(f"    - id={op.id} cmd={d.get('command')} status={d.get('status')}")

        except Exception as e:
            print(f"  ❌ エラー: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("  ⚠️ FIREBASE_UID未設定")

    # 5. get_pending_operations() テスト
    print("\n--- 5. get_pending_operations() テスト ---")
    try:
        # uid指定なし（全ユーザー走査）
        all_pending = fc.get_pending_operations()
        print(f"  📋 uid指定なし: {len(all_pending)}件")
        for op in all_pending:
            print(f"    - [{op.get('uid', '?')[:8]}] {op.get('command')} status={op.get('status')}")
    except Exception as e:
        print(f"  ❌ uid指定なし失敗: {e}")
        import traceback
        traceback.print_exc()

    try:
        # uid指定あり
        if firebase_uid:
            uid_pending = fc.get_pending_operations(uid=firebase_uid)
            print(f"  📋 uid指定あり: {len(uid_pending)}件")
            for op in uid_pending:
                print(f"    - {op.get('command')} status={op.get('status')} id={op.get('id')}")
    except Exception as e:
        print(f"  ❌ uid指定あり失敗: {e}")
        import traceback
        traceback.print_exc()

    # 6. api_keys確認
    print("\n--- 6. api_keys確認 ---")
    if firebase_uid:
        try:
            keys = fc.get_api_keys(firebase_uid)
            if keys:
                print(f"  ✅ api_keys取得成功")
                for k, v in keys.items():
                    masked = str(v)[:8] + "..." if v else "(空)"
                    print(f"    - {k}: {masked}")
            else:
                print("  ⚠️ api_keysドキュメントが存在しません")
        except Exception as e:
            print(f"  ❌ api_keys取得失敗: {e}")

    # 7. X API認証情報テスト
    print("\n--- 7. X API認証テスト ---")
    if firebase_uid:
        try:
            creds = fc.get_user_x_credentials(firebase_uid)
            if creds:
                print("  ✅ Firestore X認証情報:")
                for k, v in creds.items():
                    masked = str(v)[:8] + "..." if v else "(空)"
                    print(f"    - {k}: {masked}")

                # 実際にX APIで認証テスト
                if creds.get("api_key") and creds.get("access_token"):
                    try:
                        import tweepy
                        client = tweepy.Client(
                            consumer_key=creds["api_key"],
                            consumer_secret=creds["api_secret"],
                            access_token=creds["access_token"],
                            access_token_secret=creds["access_token_secret"],
                            wait_on_rate_limit=True
                        )
                        me = client.get_me()
                        if me and me.data:
                            print(f"  ✅ X API認証成功: @{me.data.username} (id={me.data.id})")
                        else:
                            print("  ❌ X API認証: get_me()がデータを返しませんでした")
                    except Exception as e:
                        print(f"  ❌ X API認証失敗: {e}")
            else:
                print("  ⚠️ FirestoreにX認証情報なし")
        except Exception as e:
            print(f"  ❌ X認証情報取得失敗: {e}")

    print("\n" + "=" * 60)
    print("🏁 診断完了")
    print("=" * 60)


if __name__ == "__main__":
    main()
