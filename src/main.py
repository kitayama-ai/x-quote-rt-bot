"""
X Auto Post System — メインCLIエントリーポイント

usage:
    python -m src.main generate --account 1 [--dry-run]
    python -m src.main post --account 1
    python -m src.main curate --account 1 [--dry-run]
    python -m src.main curate-post --account 1
    python -m src.main notify-test
    python -m src.main metrics --account 1
"""
import argparse
import sys
import json
from datetime import datetime
from pathlib import Path

from src.config import Config, PROJECT_ROOT


def cmd_generate(args):
    """投稿案を生成"""
    from src.generate.post_generator import PostGenerator, save_daily_output
    from src.notify.discord_notifier import DiscordNotifier

    config = Config(f"account_{args.account}")
    generator = PostGenerator(config)

    print(f"🤖 投稿生成開始 — {config.account_name} ({config.account_handle})")
    print(f"📋 モード: {config.mode}")

    # 過去投稿を取得（重複チェック用）
    past_posts = []
    if not args.dry_run:
        try:
            from src.post.x_poster import XPoster
            poster = XPoster(config)
            recent = poster.get_recent_tweets(max_results=10)
            past_posts = [t["text"] for t in recent]
            print(f"📚 過去投稿{len(past_posts)}件を取得（重複チェック用）")
        except Exception as e:
            print(f"⚠️ 過去投稿取得スキップ: {e}")

    # 生成
    posts = generator.generate_daily_posts(past_posts=past_posts)

    if not posts:
        print("❌ 投稿が生成されませんでした")
        return

    # 結果表示
    print(f"\n{'='*50}")
    print(f"📝 生成結果: {len(posts)}本")
    print(f"{'='*50}")

    from src.analyze.scorer import PostScorer
    scorer = PostScorer()

    for i, post in enumerate(posts, 1):
        score = post.get("score")
        safety = post.get("safety")

        print(f"\n--- 投稿 {i} [{post['type']}] {post['time']} ---")
        print(post["text"])
        print()
        if score:
            print(scorer.format_score(score))
        if safety:
            from src.post.safety_checker import SafetyChecker
            checker = SafetyChecker(config.safety_rules)
            print(checker.format_result(safety))

    # ファイルに保存
    output_path = save_daily_output(posts)

    # Discord通知
    if not args.dry_run:
        notifier = DiscordNotifier(config.discord_webhook_account or config.discord_webhook_general)
        notifier.notify_daily_posts(
            account_name=config.account_name,
            account_handle=config.account_handle,
            posts=posts
        )
        print("\n📨 Discord通知を送信しました")
    else:
        print("\n🔒 ドライランモード: Discord通知はスキップ")


def cmd_post(args):
    """予約投稿を実行"""
    from src.post.x_poster import XPoster
    from src.post.scheduler import Scheduler
    from src.post.safety_checker import SafetyChecker
    from src.notify.discord_notifier import DiscordNotifier

    config = Config(f"account_{args.account}")
    poster = XPoster(config)
    scheduler = Scheduler(config)
    safety_checker = SafetyChecker(config.safety_rules)
    notifier = DiscordNotifier(config.discord_webhook_account or config.discord_webhook_general)

    print(f"📤 投稿チェック — {config.account_name} ({config.account_handle})")

    # アカウント確認
    try:
        me = poster.verify_credentials()
        print(f"✅ アカウント確認: @{me['username']}")
    except Exception as e:
        print(f"❌ アカウント確認失敗: {e}")
        notifier.notify_error("アカウント確認失敗", str(e))
        return

    # 保留中の投稿を取得
    pending = scheduler.get_pending_posts()
    if not pending:
        print("📭 投稿待ちなし")
        return

    print(f"📋 {len(pending)}件の投稿待ち")

    for post in pending:
        if not scheduler.should_post_now(post):
            print(f"⏰ [{post['slot']}] まだ投稿時間帯ではない。スキップ。")
            continue

        # 安全チェック最終確認
        safety = safety_checker.check(post["text"])
        if not safety.is_safe:
            print(f"⛔ 安全チェック不合格: {safety.violations}")
            notifier.notify_safety_alert(
                config.account_name, post["text"], safety.violations
            )
            continue

        # モード判定
        score_total = post.get("score", {}).get("total", 0)
        if config.mode == "manual_approval":
            print(f"🔒 手動承認モード: Discordで承認してから手動実行してください")
            continue
        elif config.mode == "semi_auto" and score_total < config.auto_post_min_score:
            print(f"🔒 スコア{score_total}は閾値{config.auto_post_min_score}未満。承認が必要。")
            continue

        # 投稿実行
        try:
            result = poster.post_tweet(post["text"])
            tweet_id = result["id"]

            scheduler.mark_as_posted(post["_filepath"], post["slot"], tweet_id)
            notifier.notify_post_completed(config.account_name, post["text"], tweet_id)
            print(f"✅ 投稿完了: {tweet_id}")
        except Exception as e:
            print(f"❌ 投稿エラー: {e}")
            notifier.notify_error("投稿エラー", str(e))


def cmd_notify_test(args):
    """Discord通知テスト"""
    from src.notify.discord_notifier import DiscordNotifier

    config = Config(f"account_{args.account}")
    webhook = config.discord_webhook_account or config.discord_webhook_general

    if not webhook:
        print("❌ DISCORD_WEBHOOK が設定されていません")
        return

    notifier = DiscordNotifier(webhook)
    success = notifier.send(content=f"🧪 通知テスト — {config.account_name} ({config.account_handle})\n接続成功！")

    if success:
        print("✅ Discord通知テスト成功")
    else:
        print("❌ Discord通知テスト失敗")


def cmd_curate(args):
    """引用RT投稿文を生成（キューから処理）"""
    from src.collect.queue_manager import QueueManager
    from src.generate.quote_generator import QuoteGenerator
    from src.notify.discord_notifier import DiscordNotifier
    from src.post.mix_planner import MixPlanner

    config = Config(f"account_{args.account}")
    queue = QueueManager()
    generator = QuoteGenerator(config)
    planner = MixPlanner()

    print(f"🔄 引用RT生成開始 — {config.account_name} ({config.account_handle})")

    # キューの状態確認
    stats = queue.stats()
    print(f"📊 キュー: pending={stats['pending']} / approved={stats['approved']} / posted_today={stats['posted_today']}")

    # 承認済みツイートを取得
    approved = queue.get_approved()
    if not approved:
        pending = queue.get_pending()
        if pending:
            print(f"⏳ {len(pending)}件が承認待ち。--approve-all で一括承認するか、tools/add_tweet.py --approve-all を実行してください")
        else:
            print("📭 キューが空です。tools/add_tweet.py でURLを追加してください")
        return

    print(f"✅ 承認済み{len(approved)}件を処理します")

    # 過去投稿を取得（重複チェック用）
    past_posts = []
    if not args.dry_run:
        try:
            from src.post.x_poster import XPoster
            poster = XPoster(config)
            recent = poster.get_recent_tweets(max_results=10)
            past_posts = [t["text"] for t in recent]
        except Exception:
            pass

    # 各ツイートの引用RTコメントを生成
    results = []
    for item in approved:
        if not item.get("text"):
            print(f"  ⚠️ @{item['author_username']} のテキストが空。スキップ")
            continue

        print(f"  🔄 @{item['author_username']}: {item['text'][:60]}...")

        result = generator.generate(
            original_text=item["text"],
            author_username=item.get("author_username", ""),
            author_name=item.get("author_name", ""),
            likes=item.get("likes", 0),
            retweets=item.get("retweets", 0),
            past_posts=past_posts,
        )

        if result.get("text"):
            # キューに生成テキストを保存
            score_dict = None
            if result.get("score"):
                score_dict = {
                    "total": result["score"].total,
                    "rank": result["score"].rank,
                }
            queue.set_generated(
                tweet_id=item["tweet_id"],
                text=result["text"],
                template_id=result["template_id"],
                score=score_dict,
            )

            print(f"    ✅ 生成完了 [{result['template_id']}] スコア: {result['score'].total if result.get('score') else '?'}")
            print(f"    📝 {result['text'][:80]}...")
            results.append({**result, "tweet_id": item["tweet_id"]})
            past_posts.append(result["text"])
        else:
            print(f"    ❌ 生成失敗")

    print(f"\n{'='*50}")
    print(f"📝 生成結果: {len(results)}/{len(approved)}件")
    print(f"{'='*50}")

    # 投稿プラン表示
    plan = planner.plan_daily(available_quotes=len(results))
    print(f"\n{planner.format_plan(plan)}")

    # Discord通知
    if not args.dry_run and results:
        webhook = config.discord_webhook_account or config.discord_webhook_general
        if webhook:
            notifier = DiscordNotifier(webhook)
            notifier.notify_curate_results(
                account_name=config.account_name,
                results=results,
                plan=plan,
            )
            print("\n📨 Discord通知を送信しました")
    elif args.dry_run:
        print("\n🔒 ドライランモード: Discord通知はスキップ")


def cmd_curate_post(args):
    """引用RT投稿を実行（生成済みキューから）"""
    from src.collect.queue_manager import QueueManager
    from src.post.x_poster import XPoster
    from src.post.safety_checker import SafetyChecker
    from src.notify.discord_notifier import DiscordNotifier

    config = Config(f"account_{args.account}")
    queue = QueueManager()
    poster = XPoster(config)
    safety_checker = SafetyChecker(config.safety_rules)
    notifier = DiscordNotifier(config.discord_webhook_account or config.discord_webhook_general)

    print(f"📤 引用RT投稿チェック — {config.account_name}")

    # アカウント確認
    try:
        me = poster.verify_credentials()
        print(f"✅ アカウント確認: @{me['username']}")
    except Exception as e:
        print(f"❌ アカウント確認失敗: {e}")
        notifier.notify_error("アカウント確認失敗", str(e))
        return

    # 生成済みの投稿を取得
    generated = queue.get_generated()
    if not generated:
        print("📭 投稿待ちなし（生成済みの引用RTがありません）")
        return

    # モード判定
    if config.mode == "manual_approval":
        print(f"🔒 手動承認モード: Discordで確認してからcurate-postを実行してください")

    # 1日の投稿上限チェック
    daily_limit = config.safety_rules.get("posting_rules", {}).get("daily_limit_per_account", 10)
    posted_today = queue.get_today_posted_count()
    remaining = daily_limit - posted_today

    if remaining <= 0:
        print(f"⛔ 本日の投稿上限（{daily_limit}件）に達しています")
        return

    print(f"📋 生成済み{len(generated)}件 / 本日残り{remaining}件")

    posted_count = 0
    for item in generated[:remaining]:
        text = item["generated_text"]
        tweet_id = item["tweet_id"]

        # 安全チェック最終確認
        safety = safety_checker.check(text, is_quote_rt=True)
        if not safety.is_safe:
            print(f"  ⛔ 安全チェック不合格 [{tweet_id}]: {safety.violations}")
            continue

        # スコア判定（semi_autoモード）
        score_total = item.get("score", {}).get("total", 0) if item.get("score") else 0
        if config.mode == "semi_auto" and score_total < config.auto_post_min_score:
            print(f"  🔒 スコア{score_total}は閾値未満。手動承認が必要。")
            continue

        # 投稿実行
        try:
            result = poster.post_tweet(
                text=text,
                quote_tweet_id=tweet_id,
            )
            posted_tweet_id = result["id"]

            queue.mark_posted(tweet_id, posted_tweet_id)
            print(f"  ✅ 引用RT投稿完了: {posted_tweet_id} (元: {tweet_id})")
            posted_count += 1

        except Exception as e:
            print(f"  ❌ 投稿エラー [{tweet_id}]: {e}")
            notifier.notify_error("引用RT投稿エラー", str(e))

    print(f"\n📊 投稿結果: {posted_count}件投稿 / 本日累計{posted_today + posted_count}件")


def cmd_metrics(args):
    """メトリクス収集"""
    print("📊 メトリクス収集は Stage 3 で実装予定です")


def main():
    parser = argparse.ArgumentParser(
        description="X Auto Post System",
        prog="python -m src.main"
    )
    parser.add_argument(
        "--account", "-a",
        type=int,
        default=1,
        help="アカウント番号 (default: 1)"
    )

    subparsers = parser.add_subparsers(dest="command", help="サブコマンド")

    # 共通引数を各サブパーサーに追加するヘルパー
    def add_account_arg(sub_parser):
        sub_parser.add_argument(
            "--account", "-a", type=int, default=1,
            help="アカウント番号 (default: 1)"
        )
        return sub_parser

    # generate
    gen_parser = add_account_arg(subparsers.add_parser("generate", help="投稿案を生成"))
    gen_parser.add_argument("--dry-run", action="store_true", help="ドライランモード（通知なし）")

    # post
    add_account_arg(subparsers.add_parser("post", help="予約投稿を実行"))

    # notify-test
    add_account_arg(subparsers.add_parser("notify-test", help="Discord通知テスト"))

    # curate
    curate_parser = add_account_arg(subparsers.add_parser("curate", help="引用RT投稿文を生成（キューから処理）"))
    curate_parser.add_argument("--dry-run", action="store_true", help="ドライランモード（通知なし）")

    # curate-post
    add_account_arg(subparsers.add_parser("curate-post", help="引用RT投稿を実行（生成済みキューから）"))

    # metrics
    add_account_arg(subparsers.add_parser("metrics", help="メトリクス収集（Stage 3）"))

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "generate": cmd_generate,
        "post": cmd_post,
        "curate": cmd_curate,
        "curate-post": cmd_curate_post,
        "notify-test": cmd_notify_test,
        "metrics": cmd_metrics,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
