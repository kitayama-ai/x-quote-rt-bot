#!/usr/bin/env python3
"""
X Auto Post System — ツイートURL手動追加CLI

使用方法:
    # URLのみ（テキストは後で手動入力 or oEmbed取得）
    python tools/add_tweet.py "https://x.com/sama/status/1234567890"

    # URLとテキスト
    python tools/add_tweet.py "https://x.com/sama/status/1234567890" --text "元ツイートのテキスト"

    # URLとメモ
    python tools/add_tweet.py "https://x.com/sama/status/1234567890" --memo "GPT-5の発表について"

    # キューの状態確認
    python tools/add_tweet.py --status

    # 全pendingを一括承認
    python tools/add_tweet.py --approve-all

    # 特定のツイートを承認
    python tools/add_tweet.py --approve 1234567890
"""
import argparse
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.collect.tweet_parser import TweetParser, is_valid_tweet_url
from src.collect.queue_manager import QueueManager


def main():
    parser = argparse.ArgumentParser(
        description="海外AIバズツイートをキューに追加",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python tools/add_tweet.py "https://x.com/sama/status/1234567890"
  python tools/add_tweet.py "https://x.com/sama/status/1234567890" --text "Some tweet text" --memo "About GPT-5"
  python tools/add_tweet.py --status
  python tools/add_tweet.py --approve-all
        """
    )

    parser.add_argument("url", nargs="?", help="ツイートURL")
    parser.add_argument("--text", "-t", default="", help="ツイートのテキスト（任意）")
    parser.add_argument("--memo", "-m", default="", help="収集メモ（任意）")
    parser.add_argument("--status", "-s", action="store_true", help="キュー状態を表示")
    parser.add_argument("--approve-all", action="store_true", help="全pendingを承認")
    parser.add_argument("--approve", type=str, help="指定ツイートIDを承認")
    parser.add_argument("--skip", type=str, help="指定ツイートIDをスキップ")
    parser.add_argument("--list", "-l", action="store_true", help="pending一覧を表示")

    args = parser.parse_args()
    queue = QueueManager()

    # === 状態表示 ===
    if args.status:
        stats = queue.stats()
        print("📊 キュー状態:")
        print(f"  待機中 (pending):  {stats['pending']}件")
        print(f"  承認済 (approved): {stats['approved']}件")
        print(f"  スキップ:          {stats['skipped']}件")
        print(f"  投稿済 (total):    {stats['posted_total']}件")
        print(f"  投稿済 (today):    {stats['posted_today']}件")
        return

    # === 一覧表示 ===
    if args.list:
        pending = queue.get_all_pending()
        if not pending:
            print("キューは空です")
            return
        for i, item in enumerate(pending, 1):
            status_icon = {"pending": "⏳", "approved": "✅", "skipped": "⏭️", "posted": "📤"}.get(item["status"], "❓")
            text_preview = item.get("text", "")[:50] or "(テキスト未設定)"
            print(f"  {i}. {status_icon} @{item['author_username']} [{item['tweet_id']}]")
            print(f"     {text_preview}")
            if item.get("memo"):
                print(f"     📝 {item['memo']}")
            print()
        return

    # === 一括承認 ===
    if args.approve_all:
        count = queue.approve_all_pending()
        print(f"✅ {count}件を承認しました")
        return

    # === 個別承認 ===
    if args.approve:
        if queue.approve(args.approve):
            print(f"✅ ツイート {args.approve} を承認しました")
        else:
            print(f"❌ ツイート {args.approve} が見つかりません")
        return

    # === 個別スキップ ===
    if args.skip:
        if queue.skip(args.skip):
            print(f"⏭️ ツイート {args.skip} をスキップしました")
        else:
            print(f"❌ ツイート {args.skip} が見つかりません")
        return

    # === URL追加 ===
    if not args.url:
        parser.print_help()
        return

    url = args.url.strip()

    if not is_valid_tweet_url(url):
        print(f"❌ 無効なツイートURL: {url}")
        print("   対応形式: https://x.com/username/status/1234567890")
        sys.exit(1)

    try:
        tweet = TweetParser.from_url(url, text=args.text, memo=args.memo)
        added = queue.add(tweet)

        if added:
            print(f"✅ キューに追加しました:")
            print(f"   ID:     {tweet.tweet_id}")
            print(f"   Author: @{tweet.author_username}")
            print(f"   URL:    {tweet.url}")
            if tweet.text:
                print(f"   Text:   {tweet.text[:80]}...")
            if tweet.memo:
                print(f"   Memo:   {tweet.memo}")
            print()
            stats = queue.stats()
            print(f"   📊 キュー: pending={stats['pending']} / approved={stats['approved']}")
        else:
            print(f"⚠️ すでにキューに存在します: {tweet.tweet_id}")

    except ValueError as e:
        print(f"❌ エラー: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
