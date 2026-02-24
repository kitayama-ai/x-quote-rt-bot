#!/usr/bin/env python3
"""
投稿403エラー特定診断
"""
import os, json, base64

print("🏥 X API 投稿403 — 詳細診断")
print("=" * 60)

# 1. OAuth1Session の詳細チェック
print("\n[1] OAuth1Session 認証詳細")
from requests_oauthlib import OAuth1Session
session = OAuth1Session(
    os.getenv("X_API_KEY"),
    client_secret=os.getenv("X_API_SECRET"),
    resource_owner_key=os.getenv("X_ACCOUNT_1_ACCESS_TOKEN"),
    resource_owner_secret=os.getenv("X_ACCOUNT_1_ACCESS_SECRET"),
)

# GET /2/users/me
resp = session.get("https://api.twitter.com/2/users/me")
print(f"  GET /2/users/me → {resp.status_code}")
if resp.status_code == 200:
    me = resp.json().get("data", {})
    print(f"  ユーザー: @{me.get('username')} (ID: {me.get('id')})")
    print(f"  名前: {me.get('name')}")

# 2. アプリ情報確認（Bearer Token経由）
print("\n[2] Bearer Token での読み取りテスト")
import tweepy
bt = os.getenv("TWITTER_BEARER_TOKEN", "")
client = tweepy.Client(bearer_token=bt)
try:
    tweet = client.get_tweet("1585841080431321088", tweet_fields=["public_metrics"])
    if tweet and tweet.data:
        print(f"  ✅ Bearer Token有効 (ツイート読み取りOK)")
except Exception as e:
    print(f"  ❌ Bearer Token: {e}")

# 3. 投稿テスト（実際にPOSTリクエストを送るが、テスト用テキスト）
print("\n[3] POST /2/tweets テスト（ドライラン）")
# まず空payloadでレスポンスを見る
resp_empty = session.post("https://api.twitter.com/2/tweets", json={})
print(f"  空payload → {resp_empty.status_code}: {resp_empty.text[:300]}")

# テキスト付き（実際に投稿はしない - テスト用テキストを送る）
import time
test_text = f"🧪 診断テスト投稿 {int(time.time())} — このツイートは自動削除されます"
print(f"  テストテキスト: {test_text}")
resp_post = session.post("https://api.twitter.com/2/tweets", json={"text": test_text})
print(f"  POST結果 → {resp_post.status_code}")
print(f"  レスポンス: {resp_post.text[:500]}")

if resp_post.status_code in (200, 201):
    tweet_data = resp_post.json().get("data", {})
    tweet_id = tweet_data.get("id", "")
    print(f"  ✅ 投稿成功! tweet_id={tweet_id}")
    # 自動削除
    del_resp = session.delete(f"https://api.twitter.com/2/tweets/{tweet_id}")
    print(f"  🗑️ 自動削除 → {del_resp.status_code}")
elif resp_post.status_code == 403:
    print(f"  ❌ 403 Forbidden — 詳細分析:")
    try:
        err = resp_post.json()
        print(f"     detail: {err.get('detail', 'なし')}")
        print(f"     title: {err.get('title', 'なし')}")
        print(f"     type: {err.get('type', 'なし')}")
        # 403の一般的な原因
        print(f"\n  💡 考えられる原因:")
        print(f"     1. Access Token のスコープが Read-only")
        print(f"        → X Developer Portal で Token 再生成が必要")
        print(f"     2. アカウントが制限/凍結されている")
        print(f"     3. X API Freeプランの月間投稿上限に達している")
    except:
        pass
else:
    print(f"  ⚠️ 予期しないステータス: {resp_post.status_code}")

# 4. tweepy Client経由でも試す
print("\n[4] tweepy.Client (OAuth 1.0a User Context) でのPOSTテスト")
try:
    user_client = tweepy.Client(
        consumer_key=os.getenv("X_API_KEY"),
        consumer_secret=os.getenv("X_API_SECRET"),
        access_token=os.getenv("X_ACCOUNT_1_ACCESS_TOKEN"),
        access_token_secret=os.getenv("X_ACCOUNT_1_ACCESS_SECRET"),
    )
    test_text2 = f"🧪 tweepy診断 {int(time.time())}"
    result = user_client.create_tweet(text=test_text2)
    if result and result.data:
        tweet_id2 = result.data["id"]
        print(f"  ✅ tweepy投稿成功! tweet_id={tweet_id2}")
        user_client.delete_tweet(tweet_id2)
        print(f"  🗑️ 自動削除完了")
except tweepy.errors.Forbidden as e:
    print(f"  ❌ tweepy 403: {e}")
except Exception as e:
    print(f"  ❌ tweepy エラー: {e}")

# 5. 引用RTテスト
print("\n[5] 引用RT POST テスト")
resp_qt = session.post("https://api.twitter.com/2/tweets", json={
    "text": f"🧪 引用RTテスト {int(time.time())}",
    "quote_tweet_id": "1585841080431321088"
})
print(f"  引用RT POST → {resp_qt.status_code}")
print(f"  レスポンス: {resp_qt.text[:300]}")
if resp_qt.status_code in (200, 201):
    qt_id = resp_qt.json().get("data", {}).get("id", "")
    print(f"  ✅ 引用RT成功! tweet_id={qt_id}")
    del_resp2 = session.delete(f"https://api.twitter.com/2/tweets/{qt_id}")
    print(f"  🗑️ 自動削除 → {del_resp2.status_code}")

print("\n" + "=" * 60)
print("診断完了")
