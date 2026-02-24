#!/usr/bin/env python3
"""
ミニマム診断ツール — 全コンポーネントを独立テスト
各テストは他の結果に依存しない。全部実行して一覧表示する。
"""
import os
import json
import sys

RESULTS = []

def test(name):
    """テスト結果を記録するデコレータ"""
    def decorator(func):
        def wrapper():
            print(f"\n{'='*60}")
            print(f"🧪 {name}")
            print(f"{'='*60}")
            try:
                result = func()
                RESULTS.append(("✅", name, result or "OK"))
                print(f"  → ✅ {result or 'OK'}")
            except Exception as e:
                RESULTS.append(("❌", name, str(e)))
                print(f"  → ❌ {e}")
        return wrapper
    return decorator


# ===== TEST 1: 環境変数チェック =====
@test("環境変数チェック")
def test_env():
    required = [
        "X_API_KEY", "X_API_SECRET",
        "X_ACCOUNT_1_ACCESS_TOKEN", "X_ACCOUNT_1_ACCESS_SECRET",
        "FIREBASE_CREDENTIALS_BASE64", "FIREBASE_UID",
        "TWITTER_BEARER_TOKEN",
    ]
    missing = [k for k in required if not os.getenv(k)]
    present = [k for k in required if os.getenv(k)]
    for k in present:
        val = os.getenv(k, "")
        print(f"  ✅ {k} = {val[:8]}...")
    if missing:
        raise RuntimeError(f"未設定: {', '.join(missing)}")
    return f"{len(present)}/{len(required)} 全て設定済み"


# ===== TEST 2: Firebase Admin SDK 初期化 =====
@test("Firebase Admin SDK 初期化")
def test_firebase_init():
    import firebase_admin
    from firebase_admin import credentials, firestore
    cred_b64 = os.getenv("FIREBASE_CREDENTIALS_BASE64", "")
    cred_json = json.loads(base64.b64decode(cred_b64).decode())
    cred = credentials.Certificate(cred_json)
    app = firebase_admin.initialize_app(cred)
    db = firestore.client()
    return f"プロジェクト: {cred_json.get('project_id', '?')}"


# ===== TEST 3: Firestore — usersコレクション内のドキュメント一覧 =====
@test("Firestore: usersコレクション ドキュメント一覧")
def test_firestore_users():
    from firebase_admin import firestore
    db = firestore.client()
    users = list(db.collection("users").stream())
    if not users:
        print("  ⚠️ usersコレクションにドキュメントが0件")
        print("  → サブコレクションのみ存在している可能性")
    for u in users:
        data = u.to_dict()
        print(f"  📄 {u.id}: {json.dumps(data, ensure_ascii=False, default=str)[:150]}")
    return f"{len(users)}件のユーザードキュメント"


# ===== TEST 4: Firestore — FIREBASE_UID のサブコレクション =====
@test("Firestore: FIREBASE_UID直下のoperation_requests")
def test_firestore_uid_ops():
    from firebase_admin import firestore
    db = firestore.client()
    uid = os.getenv("FIREBASE_UID", "")
    docs = list(db.collection("users").document(uid).collection("operation_requests").limit(10).stream())
    for d in docs:
        data = d.to_dict()
        print(f"  📄 {d.id}: status={data.get('status')}, command={data.get('command')}, requested_at={data.get('requested_at')}")
    if not docs:
        print(f"  ⚠️ users/{uid}/operation_requests にドキュメントなし")
    return f"{len(docs)}件 (UID: {uid[:8]}...)"


# ===== TEST 5: Firestore — 全ユーザーのoperation_requests探索 =====
@test("Firestore: 全サブコレクション探索（collection_group代替）")
def test_firestore_all_ops():
    from firebase_admin import firestore
    db = firestore.client()
    # Firebase Admin SDKはセキュリティルール無視なので直接アクセス可能
    # まず collection_group を試す（インデックス有無に関わらず Admin SDK ならいける場合あり）
    found_uids = set()
    try:
        all_ops = list(db.collection_group("operation_requests").limit(20).stream())
        for doc in all_ops:
            path = doc.reference.path
            data = doc.to_dict()
            uid_from_path = path.split("/")[1] if len(path.split("/")) > 1 else "?"
            found_uids.add(uid_from_path)
            print(f"  📄 [{uid_from_path[:8]}...] {doc.id}: status={data.get('status')}, command={data.get('command')}")
        env_uid = os.getenv("FIREBASE_UID", "")
        if found_uids and env_uid not in found_uids:
            print(f"\n  🚨 FIREBASE_UID ({env_uid[:8]}...) が見つかったUID群 ({[u[:8] for u in found_uids]}) に含まれていない！")
            print(f"  → GitHubシークレット FIREBASE_UID を以下のいずれかに更新する必要あり:")
            for u in found_uids:
                print(f"     {u}")
        return f"{len(all_ops)}件 / {len(found_uids)}ユーザー"
    except Exception as e:
        print(f"  ⚠️ collection_group失敗: {e}")
        return f"collection_groupクエリ失敗（インデックス要）"


# ===== TEST 6: X API — OAuth1Session で POST 可能か =====
@test("X API: OAuth1Session 認証テスト (POST可能か)")
def test_x_oauth():
    from requests_oauthlib import OAuth1Session
    session = OAuth1Session(
        os.getenv("X_API_KEY"),
        client_secret=os.getenv("X_API_SECRET"),
        resource_owner_key=os.getenv("X_ACCOUNT_1_ACCESS_TOKEN"),
        resource_owner_secret=os.getenv("X_ACCOUNT_1_ACCESS_SECRET"),
    )
    # GET /2/users/me を試す（Freeプランだと401になるかも）
    resp = session.get("https://api.twitter.com/2/users/me")
    print(f"  GET /2/users/me → {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json().get("data", {})
        return f"認証OK: @{data.get('username', '?')}"
    elif resp.status_code in (401, 403):
        # Freeプラン制限。でもPOSTは動く可能性あり
        print(f"  → Freeプラン制限 ({resp.status_code}). POST /2/tweets は別途テスト")
        return f"GET制限 ({resp.status_code}) — Freeプラン想定内"
    else:
        raise RuntimeError(f"予期しないレスポンス: {resp.status_code} {resp.text[:200]}")


# ===== TEST 7: X API — Bearer Token =====
@test("X API: Bearer Token テスト")
def test_x_bearer():
    import tweepy
    token = os.getenv("TWITTER_BEARER_TOKEN", "")
    client = tweepy.Client(bearer_token=token)
    # 公開ツイートを1件取得テスト (Elon Musk's pinned tweet)
    tweet = client.get_tweet("1585841080431321088")
    if tweet and tweet.data:
        return f"Bearer Token有効: tweet取得OK"
    raise RuntimeError("ツイート取得失敗")


# ===== TEST 8: Firestore Auth設定確認 =====
@test("Firestore: Auth設定（Xログインプロバイダー）")
def test_firebase_auth_users():
    from firebase_admin import auth
    # 最近のユーザーを列挙
    page = auth.list_users(max_results=10)
    users_info = []
    for user in page.users:
        providers = [p.provider_id for p in user.provider_data]
        users_info.append({
            "uid": user.uid,
            "email": user.email or "なし",
            "providers": providers,
            "display_name": user.display_name or "なし",
        })
        print(f"  👤 UID={user.uid[:12]}... providers={providers} email={user.email or 'なし'} name={user.display_name or 'なし'}")
    
    env_uid = os.getenv("FIREBASE_UID", "")
    match = any(u["uid"] == env_uid for u in users_info)
    if not match:
        print(f"\n  🚨 FIREBASE_UID ({env_uid[:8]}...) がAuth上のどのユーザーとも一致しない！")
    else:
        print(f"\n  ✅ FIREBASE_UID ({env_uid[:8]}...) はAuth上に存在")
    return f"{len(users_info)}ユーザー, FIREBASE_UID一致={'✅' if match else '❌'}"


# ===== 実行 =====
import base64

print("🏥 X Quote RT Bot — ミニマム診断ツール")
print(f"{'='*60}")

tests = [
    test_env,
    test_firebase_init,
    test_firestore_users,
    test_firestore_uid_ops,
    test_firestore_all_ops,
    test_x_oauth,
    test_x_bearer,
    test_firebase_auth_users,
]

for t in tests:
    t()

# サマリー
print(f"\n\n{'='*60}")
print("📋 診断サマリー")
print(f"{'='*60}")
for icon, name, result in RESULTS:
    print(f"  {icon} {name}")
    print(f"     {result}")

passed = sum(1 for r in RESULTS if r[0] == "✅")
failed = sum(1 for r in RESULTS if r[0] == "❌")
print(f"\n  結果: {passed}✅ / {failed}❌")
