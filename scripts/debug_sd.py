import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# プロジェクトルートを追加
sys.path.append('/home/ubuntu/x-quote-rt-bot')

from src.collect.socialdata_client import SocialDataClient
from src.collect.auto_collector import AutoCollector

def debug_socialdata():
    client = SocialDataClient()
    # ユーザーが実際に受け取ったクエリ
    query = '("AI agent" OR GPT-5 OR Claude OR Gemini OR "AI automation") min_faves:700 lang:en -filter:replies -filter:retweets'
    print(f"--- Calling SocialData: {query} ---")
    
    tweets = client.search(query, max_results=20)
    print(f"Results count: {len(tweets)}")
    
    for i, t in enumerate(tweets):
        fid = t.get("id_str")
        likes = t.get("favorite_count", "N/A")
        date = t.get("tweet_created_at", "N/A")
        text = t.get("full_text", "")[:50]
        user = t.get("user", {}).get("screen_name")
        print(f"[{i}] @{user} | ID: {fid} | Likes: {likes} | Date: {date} | Text: {text}...")

    # Age filter check
    collector = AutoCollector()
    cutoff = datetime.now(ZoneInfo("Asia/Tokyo"))
    print(f"Cutoff (Now-48h): {cutoff}")

if __name__ == "__main__":
    debug_socialdata()
