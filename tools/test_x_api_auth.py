#!/usr/bin/env python3
"""
X API認証テスト — 401の原因特定

Step 1: 環境変数の存在確認
Step 2: tweepy.Client で get_me() (v2 OAuth1.0a)
Step 3: OAuth1Session で GET /2/users/me (requests-oauthlib)
Step 4: Bearer Token で GET /2/users/me
Step 5: 投稿権限テスト (実際には投稿しない)
"""
import os
import sys


def main():
    print("=" * 60)
    print("🧪 X API認証 診断テスト")
    print("=" * 60)

    # ---- Step 1: 環境変数確認 ----
    print("\n--- Step 1: 環境変数 ---")
    keys = {
        "X_API_KEY": os.environ.get("X_API_KEY", ""),
        "X_API_SECRET": os.environ.get("X_API_SECRET", ""),
        "X_ACCOUNT_1_ACCESS_TOKEN": os.environ.get("X_ACCOUNT_1_ACCESS_TOKEN", ""),
        "X_ACCOUNT_1_ACCESS_SECRET": os.environ.get("X_ACCOUNT_1_ACCESS_SECRET", ""),
        "TWITTER_BEARER_TOKEN": os.environ.get("TWITTER_BEARER_TOKEN", ""),
    }
    all_ok = True
    for k, v in keys.items():
        if v:
            # 最初と最後の数文字だけ表示してマスク
            masked = v[:4] + "..." + v[-4:] if len(v) > 10 else "***"
            print(f"  ✅ {k}: {masked} (len={len(v)})")
        else:
            print(f"  ❌ {k}: 未設定")
            all_ok = False

    if not all_ok:
        print("\n❌ 必要な環境変数が未設定です。GitHub Secrets を確認してください。")

    # ---- Step 2: tweepy v2 OAuth1.0a で get_me() ----
    print("\n--- Step 2: tweepy.Client.get_me() (OAuth1.0a) ---")
    try:
        import tweepy
        client = tweepy.Client(
            consumer_key=keys["X_API_KEY"],
            consumer_secret=keys["X_API_SECRET"],
            access_token=keys["X_ACCOUNT_1_ACCESS_TOKEN"],
            access_token_secret=keys["X_ACCOUNT_1_ACCESS_SECRET"],
            wait_on_rate_limit=False,
        )
        me = client.get_me()
        if me and me.data:
            print(f"  ✅ 認証成功: @{me.data.username} (id={me.data.id})")
        else:
            print(f"  ❌ get_me() が空を返した: {me}")
    except tweepy.TweepyException as e:
        print(f"  ❌ TweepyException: {e}")
        print(f"     → HTTPStatus: {getattr(e, 'response', None) and e.response.status_code}")
    except Exception as e:
        print(f"  ❌ 予期しないエラー: {e}")

    # ---- Step 3: requests-oauthlib で /2/users/me ----
    print("\n--- Step 3: OAuth1Session で GET /2/users/me ---")
    try:
        from requests_oauthlib import OAuth1Session
        session = OAuth1Session(
            keys["X_API_KEY"],
            client_secret=keys["X_API_SECRET"],
            resource_owner_key=keys["X_ACCOUNT_1_ACCESS_TOKEN"],
            resource_owner_secret=keys["X_ACCOUNT_1_ACCESS_SECRET"],
        )
        resp = session.get("https://api.twitter.com/2/users/me")
        print(f"  HTTP {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            print(f"  ✅ 認証成功: @{data.get('username')} (id={data.get('id')})")
        else:
            print(f"  ❌ エラー: {resp.text[:300]}")
    except Exception as e:
        print(f"  ❌ 予期しないエラー: {e}")

    # ---- Step 4: Bearer Token で GET /2/users/me ----
    print("\n--- Step 4: Bearer Token で GET /2/users/me ---")
    bearer = keys["TWITTER_BEARER_TOKEN"]
    if bearer:
        try:
            import requests
            resp = requests.get(
                "https://api.twitter.com/2/users/me",
                headers={"Authorization": f"Bearer {bearer}"},
            )
            print(f"  HTTP {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                print(f"  ✅ Bearer認証成功: @{data.get('username')}")
            else:
                print(f"  ❌ エラー: {resp.text[:300]}")
        except Exception as e:
            print(f"  ❌ 予期しないエラー: {e}")
    else:
        print("  ⚠️ TWITTER_BEARER_TOKEN未設定 → スキップ")

    # ---- Step 5: アプリ情報確認（API Key の組み合わせが正しいか） ----
    print("\n--- Step 5: リクエストトークン取得（API Key/Secretの疎通確認） ---")
    try:
        from requests_oauthlib import OAuth1Session
        # request_token エンドポイント — Bearer不要、API Key/Secretのみで認証
        oauth = OAuth1Session(keys["X_API_KEY"], client_secret=keys["X_API_SECRET"])
        resp = oauth.fetch_request_token("https://api.twitter.com/oauth/request_token")
        print(f"  ✅ API Key/Secret は有効 (oauth_token: {resp.get('oauth_token', '')[:10]}...)")
    except Exception as e:
        print(f"  ❌ API Key/Secret エラー: {e}")
        print(f"     → API KeyとSecretが間違っているか、アプリが無効化されている可能性")

    print("\n" + "=" * 60)
    print("📊 診断完了")
    print("=" * 60)
    print("""
【よくある原因と対処】
  401 on step2/3 + ✅ on step5 → Access Token/Secret が失効
    → X Developer Portal でトークンを Regenerate して GitHub Secrets を更新

  401 on step2/3/5 → API Key/Secret が無効
    → X Developer Portal で App の Key/Secret を確認・再生成

  401 on step4 → Bearer Token が無効または未設定
    → X Developer Portal の Bearer Token を確認
""")


if __name__ == "__main__":
    main()
