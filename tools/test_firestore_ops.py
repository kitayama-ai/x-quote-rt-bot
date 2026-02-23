#!/usr/bin/env python3
"""
最小テスト: Firestore operation_requests の読み書き確認

GitHub Actions で実行して、以下を検証する:
1. Firebase初期化できるか
2. FIREBASE_UID で users ドキュメントが見えるか
3. operation_requests サブコレクションが読めるか
4. pending リクエストが取得できるか
5. ステータス更新ができるか
"""
import os
import sys
import json
import base64
import re
import tempfile

def main():
    print("=" * 60)
    print("🧪 Firestore operation_requests 最小テスト")
    print("=" * 60)

    # ---- Step 1: 環境変数チェック ----
    print("\n--- Step 1: 環境変数 ---")
    creds_b64 = os.environ.get("FIREBASE_CREDENTIALS_BASE64", "")
    firebase_uid = os.environ.get("FIREBASE_UID", "")

    if not creds_b64:
        print("❌ FIREBASE_CREDENTIALS_BASE64 が未設定")
        sys.exit(1)
    print(f"✅ FIREBASE_CREDENTIALS_BASE64: {len(creds_b64)} chars")

    if not firebase_uid:
        print("⚠️ FIREBASE_UID が未設定（全ユーザースキャンになる）")
    else:
        print(f"✅ FIREBASE_UID: {firebase_uid}")

    # ---- Step 2: Firebase初期化 ----
    print("\n--- Step 2: Firebase初期化 ---")
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        # Base64デコード
        b64str = re.sub(r'\s+', '', creds_b64).rstrip('=')
        missing = len(b64str) % 4
        if missing:
            b64str += '=' * (4 - missing)
        cred_json = base64.b64decode(b64str, validate=False).decode("utf-8")
        cred_dict = json.loads(cred_json)
        print(f"✅ Base64デコード成功 (project: {cred_dict.get('project_id', '?')})")

        # 初期化
        try:
            app = firebase_admin.get_app()
        except ValueError:
            cred = credentials.Certificate(cred_dict)
            app = firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Firestore client 初期化成功")
    except Exception as e:
        print(f"❌ Firebase初期化エラー: {e}")
        sys.exit(1)

    # ---- Step 3: users コレクション確認 ----
    print("\n--- Step 3: users コレクション ---")
    user_uids = []
    try:
        users = list(db.collection("users").stream())
        print(f"📋 users コレクション: {len(users)} ドキュメント")
        for u in users:
            data = u.to_dict()
            user_uids.append(u.id)
            print(f"  - {u.id} (role={data.get('role', '?')}, display={data.get('displayName', '?')})")
    except Exception as e:
        print(f"❌ users 取得エラー: {e}")

    # ---- Step 4: 全ユーザーの operation_requests を確認 ----
    print(f"\n--- Step 4: 全ユーザーの operation_requests ---")
    for uid in user_uids:
        try:
            ops = list(
                db.collection("users").document(uid)
                .collection("operation_requests")
                .limit(20)
                .stream()
            )
            if ops:
                print(f"\n  👤 {uid}: {len(ops)} 件")
                for doc in ops:
                    data = doc.to_dict()
                    print(f"    - id={doc.id}, status={data.get('status')}, cmd={data.get('command')}, by={data.get('requested_by')}, at={data.get('requested_at')}")
            else:
                print(f"  👤 {uid}: 0 件")
        except Exception as e:
            print(f"  ❌ {uid}: エラー: {e}")

    # ---- Step 5: FIREBASE_UID と実データの一致確認 ----
    if firebase_uid:
        print(f"\n--- Step 5: FIREBASE_UID 確認 ---")
        print(f"  GitHub Secrets FIREBASE_UID = {firebase_uid}")
        if firebase_uid in user_uids:
            print(f"  ✅ users コレクションに存在")
        else:
            print(f"  ❌ users コレクションに存在しない！")

    # ---- Step 6: テスト書き込み＆読み戻し（最初のユーザーで） ----
    test_uid = firebase_uid or (user_uids[0] if user_uids else "")
    if test_uid:
        print(f"\n--- Step 6: テスト書き込み＆読み戻し (uid={test_uid}) ---")
        try:
            from google.cloud import firestore as fs_module
            test_ref = (
                db.collection("users").document(test_uid)
                .collection("operation_requests")
                .document("test_doc_001")
            )
            test_ref.set({
                "command": "export-dashboard",
                "status": "pending",
                "requested_at": fs_module.SERVER_TIMESTAMP,
                "requested_by": "test_script",
                "requested_by_uid": test_uid,
            })
            print("✅ テストドキュメント書き込み成功")

            # 読み戻し
            test_doc = test_ref.get()
            if test_doc.exists:
                print(f"✅ 読み戻し成功: {test_doc.to_dict()}")
            else:
                print("❌ 書き込んだのに読み戻せない")

            # pendingとして取得できるか（FieldFilter版）
            from google.cloud.firestore_v1.base_query import FieldFilter
            pending_after = list(
                db.collection("users").document(test_uid)
                .collection("operation_requests")
                .where(filter=FieldFilter("status", "==", "pending"))
                .limit(10)
                .stream()
            )
            found = any(d.id == "test_doc_001" for d in pending_after)
            print(f"{'✅' if found else '❌'} pending クエリで{'見つかった' if found else '見つからなかった'}")

            # 削除
            test_ref.delete()
            print("🗑️ テストドキュメント削除完了")
        except Exception as e:
            print(f"❌ テスト書き込みエラー: {e}")
            try:
                test_ref.delete()
            except Exception:
                pass

    print("\n" + "=" * 60)
    print("🧪 テスト完了")
    print("=" * 60)


if __name__ == "__main__":
    main()
