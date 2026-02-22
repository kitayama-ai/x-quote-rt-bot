"""
X Auto Post System — メインCLIエントリーポイント

usage:
    python -m src.main generate --account 1 [--dry-run]
    python -m src.main post --account 1
    python -m src.main curate --account 1 [--dry-run]
    python -m src.main curate-post --account 1
    python -m src.main collect [--dry-run] [--auto-approve] [--min-likes 500]
    python -m src.main import-urls --account 1 [--auto-approve]
    python -m src.main setup-sheets --account 1
    python -m src.main notify-test
    python -m src.main metrics --account 1 [--days 7]
    python -m src.main weekly-pdca --account 1
    python -m src.main sync-queue --direction full --account 1
    python -m src.main sync-settings --account 1
    python -m src.main export-dashboard --account 1
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


def cmd_collect(args):
    """バズツイートを自動収集（パターンB: X API v2）"""
    from src.collect.auto_collector import AutoCollector
    from src.notify.discord_notifier import DiscordNotifier

    print("🔍 バズツイート自動収集開始（X API v2）")

    # スプシから設定を読み込み（環境変数が設定されていれば）
    sheet_settings = {}
    sync = None
    try:
        from src.sheets.sheets_client import SheetsClient
        from src.sheets.queue_sync import QueueSync
        config_for_sheets = Config(f"account_{args.account}")
        if config_for_sheets.spreadsheet_id:
            sheets = SheetsClient(config_for_sheets)
            sync = QueueSync(sheets)
            sheet_settings = sync.read_settings()
            if sheet_settings:
                print(f"📋 シート設定を読み込み: {sheet_settings}")
    except Exception as e:
        print(f"⚠️ シート設定の読み込みスキップ: {e}")

    # プリファレンス同期（Sheets → ローカルJSON）
    if sync:
        try:
            pref_result = sync.sync_preferences()
            if pref_result["updated_keys"]:
                print(f"🎯 プリファレンス同期(Sheets): {', '.join(pref_result['updated_keys'])}")
        except Exception as e:
            print(f"⚠️ プリファレンス同期スキップ: {e}")

    # Firebase同期（ダッシュボード操作の反映）
    try:
        import os as _os
        from src.firestore.firestore_client import FirestoreClient
        from src.firestore.firebase_sync import FirebaseSync
        fc = FirestoreClient()
        fb_sync = FirebaseSync(fc)
        # キュー決定を同期
        q_result = fb_sync.sync_queue_decisions()
        if q_result["approved"] or q_result["skipped"]:
            print(f"🔥 Firebase同期: 承認{q_result['approved']}件, スキップ{q_result['skipped']}件")
        # プリファレンス同期
        fb_uid = _os.getenv("FIREBASE_UID", "")
        if fb_uid:
            p_result = fb_sync.sync_selection_preferences(fb_uid)
            if p_result["updated_keys"]:
                print(f"🎯 Firebase設定同期: {', '.join(p_result['updated_keys'])}")
    except ImportError:
        pass  # firebase-admin 未インストール時はスキップ
    except Exception as e:
        print(f"⚠️ Firebase同期スキップ: {e}")

    # CLI引数がなければシート設定を使用
    effective_min_likes = args.min_likes or sheet_settings.get("min_likes")
    effective_auto_approve = args.auto_approve or sheet_settings.get("auto_approve", False)
    effective_max_tweets = args.max_tweets if args.max_tweets != 50 else sheet_settings.get("max_tweets", 50)

    try:
        collector = AutoCollector()
    except ValueError as e:
        print(f"❌ {e}")
        print("💡 .env に TWITTER_BEARER_TOKEN=your_token を追加してください")
        return

    result = collector.collect(
        min_likes=effective_min_likes,
        max_tweets=effective_max_tweets,
        auto_approve=effective_auto_approve,
        dry_run=args.dry_run,
    )

    # 結果表示
    print(f"\n{'='*50}")
    print(collector.format_result(result))
    print(f"{'='*50}")

    if args.dry_run:
        print("\n🔒 ドライランモード: キューへの追加はスキップ")
        return

    # 収集結果をスプシに同期
    if sync:
        try:
            sync.sync_collection_log(result)
            sync.sync_to_sheet()
            sync.sync_dashboard(collection_result=result)
            print("📊 スプレッドシートに同期しました")
        except Exception as e:
            print(f"⚠️ スプシ同期エラー: {e}")

    # Discord通知
    if result["added"] > 0:
        try:
            config = Config(f"account_{args.account}")
            webhook = config.discord_webhook_account or config.discord_webhook_general
            if webhook:
                notifier = DiscordNotifier(webhook)
                msg = (
                    f"📥 **バズツイート自動収集完了**\n"
                    f"API取得: {result['fetched']}件\n"
                    f"フィルタ後: {result['filtered']}件\n"
                    f"キュー追加: {result['added']}件\n"
                    f"重複スキップ: {result['skipped_dup']}件"
                )
                if result["tweets"]:
                    msg += "\n\n**追加ツイート（上位5件）:**"
                    for t in result["tweets"][:5]:
                        msg += f"\n• @{t.author_username} ({t.likes:,}❤) {t.text[:60]}..."
                notifier.send(content=msg)
                print("\n📨 Discord通知を送信しました")
        except Exception as e:
            print(f"⚠️ Discord通知送信エラー: {e}")

    if effective_auto_approve and result["added"] > 0:
        print(f"\n✅ {result['added']}件を自動承認しました")
        print("💡 次のステップ: python -m src.main curate --account 1")
    elif result["added"] > 0:
        print(f"\n⏳ {result['added']}件がキューに追加されました（承認待ち）")
        print("💡 承認: python tools/add_tweet.py --approve-all")


def cmd_metrics(args):
    """メトリクス収集 & Discord通知"""
    from src.analyze.metrics_collector import MetricsCollector
    from src.notify.discord_notifier import DiscordNotifier

    config = Config(f"account_{args.account}")
    print(f"📊 メトリクス収集開始 — {config.account_name} ({config.account_handle})")

    try:
        collector = MetricsCollector(config)
    except Exception as e:
        print(f"❌ X API初期化エラー: {e}")
        return

    # メトリクス収集
    days = getattr(args, 'days', 7)
    metrics = collector.collect_recent(days=days)

    if not metrics:
        print("📭 メトリクスが取得できませんでした（投稿がないか、API接続に問題あり）")
        return

    # サマリー計算
    summary = collector.calculate_summary(metrics)

    # 結果表示
    print(f"\n{'='*50}")
    print(f"📊 メトリクスサマリー（直近{days}日間）")
    print(f"{'='*50}")
    print(f"  投稿数:            {summary.get('post_count', 0)}本")
    print(f"  平均いいね:        {summary.get('avg_likes', 0)}")
    print(f"  平均RT:            {summary.get('avg_retweets', 0)}")
    print(f"  平均リプライ:      {summary.get('avg_replies', 0)}")
    print(f"  エンゲージメント率: {summary.get('engagement_rate', 0)}%")
    print(f"  総インプレッション: {summary.get('total_impressions', 0):,}")
    print(f"\n  🏆 ベスト投稿: {summary.get('best_tweet', '—')}")
    print(f"     👍 {summary.get('best_likes', 0)}いいね")

    # ファイル保存
    filepath = collector.save_metrics(metrics)

    # Discord通知
    webhook = config.discord_webhook_metrics or config.discord_webhook_general
    if webhook:
        notifier = DiscordNotifier(webhook)
        notifier.notify_metrics(config.account_name, summary)
        print("\n📨 Discord通知を送信しました")


def cmd_weekly_pdca(args):
    """週次PDCA（メトリクス収集→レポート→マスターデータ更新→Discord通知）"""
    from src.analyze.metrics_collector import MetricsCollector
    from src.pdca.weekly_report import WeeklyReporter
    from src.pdca.master_updater import MasterUpdater
    from src.notify.discord_notifier import DiscordNotifier

    config = Config(f"account_{args.account}")
    print(f"📈 週次PDCA開始 — {config.account_name}")

    # 1. メトリクス収集
    print("\n── STEP 1: メトリクス収集 ──")
    try:
        collector = MetricsCollector(config)
        metrics = collector.collect_recent(days=7)
        collector.save_metrics(metrics)
        print(f"  ✅ {len(metrics)}件のメトリクスを収集")
    except Exception as e:
        print(f"  ❌ メトリクス収集エラー: {e}")
        metrics = []

    # 2. 週次レポート生成
    print("\n── STEP 2: 週次レポート生成 ──")
    try:
        reporter = WeeklyReporter(config)
        report = reporter.generate_report(metrics)
        reporter.save_report(report)
        print("  ✅ レポート生成完了")
    except Exception as e:
        print(f"  ❌ レポート生成エラー: {e}")
        report = f"レポート生成エラー: {e}"

    # 3. マスターデータ更新
    print("\n── STEP 3: マスターデータ更新 ──")
    try:
        updater = MasterUpdater(config)
        updater.update_from_metrics(metrics)
        print("  ✅ マスターデータ更新完了")
    except Exception as e:
        print(f"  ⚠️ マスターデータ更新スキップ: {e}")

    # 3.5. 選定PDCA
    print("\n── STEP 3.5: 選定PDCA ──")
    try:
        from src.pdca.preference_updater import PreferenceUpdater
        pref_updater = PreferenceUpdater()
        pref_analysis = pref_updater.analyze_feedback()
        if pref_analysis["total_decisions"] > 0:
            pref_changes = pref_updater.auto_update()
            print(f"  ✅ 選定PDCA: {pref_changes['summary']}")
        else:
            print("  ℹ️ 選定PDCA: フィードバックデータなし")
    except Exception as e:
        print(f"  ⚠️ 選定PDCAスキップ: {e}")

    # 4. Discord通知
    print("\n── STEP 4: Discord通知 ──")
    webhook = config.discord_webhook_metrics or config.discord_webhook_general
    if webhook:
        notifier = DiscordNotifier(webhook)
        notifier.notify_weekly_report(config.account_name, report)
        print("  ✅ Discord通知送信完了")
    else:
        print("  ⚠️ Discord Webhook未設定")

    print(f"\n✅ 週次PDCA完了")


def cmd_import_urls(args):
    """スプレッドシートからURLを一括インポート（パターンA）"""
    from src.sheets.sheets_client import SheetsClient
    from src.sheets.url_importer import URLImporter
    from src.notify.discord_notifier import DiscordNotifier

    config = Config(f"account_{args.account}")
    print(f"📥 スプレッドシートからURL一括インポート — {config.account_name}")

    try:
        sheets = SheetsClient(config)
    except ValueError as e:
        print(f"❌ {e}")
        print("💡 .env に SPREADSHEET_ID と GOOGLE_CREDENTIALS_BASE64 を追加してください")
        return

    importer = URLImporter(sheets)
    result = importer.import_urls(auto_approve=args.auto_approve)

    print(f"\n{'='*50}")
    print(importer.format_result(result))
    print(f"{'='*50}")

    # Discord通知
    if result["added"] > 0:
        webhook = config.discord_webhook_account or config.discord_webhook_general
        if webhook:
            notifier = DiscordNotifier(webhook)
            notifier.send(content=(
                f"📥 **スプシからURL一括インポート完了**\n"
                f"追加: {result['added']}件 / 重複: {result['skipped_dup']}件 / 無効: {result['invalid']}件"
            ))
            print("\n📨 Discord通知を送信しました")

    if result["added"] > 0:
        if args.auto_approve:
            print(f"\n✅ {result['added']}件を自動承認しました")
        print("💡 次のステップ: python -m src.main curate --account 1")


def cmd_setup_sheets(args):
    """スプレッドシートの初期セットアップ"""
    from src.sheets.sheets_client import SheetsClient

    config = Config(f"account_{args.account}")
    print(f"🔧 スプレッドシート初期セットアップ — {config.account_name}")

    try:
        sheets = SheetsClient(config)
    except ValueError as e:
        print(f"❌ {e}")
        return

    created = sheets.setup_sheets()
    if created:
        print(f"✅ 作成したシート: {', '.join(created)}")
    else:
        print("✅ 全シート作成済みです（変更なし）")


def cmd_sync_queue(args):
    """キュー <-> スプレッドシート双方向同期（パターンB管理用）"""
    from src.sheets.sheets_client import SheetsClient
    from src.sheets.queue_sync import QueueSync

    config = Config(f"account_{args.account}")
    print(f"🔄 キュー同期開始 — 方向: {args.direction}")

    try:
        sheets = SheetsClient(config)
    except ValueError as e:
        print(f"❌ {e}")
        print("💡 .env に SPREADSHEET_ID と GOOGLE_CREDENTIALS_BASE64 を追加してください")
        return

    sync = QueueSync(sheets)

    if args.direction == "to_sheet":
        result = sync.sync_to_sheet()
        sync.sync_dashboard()
        print(f"✅ キュー→スプシ同期完了: {result['synced']}件")
        print(f"   ステータス内訳: {result['statuses']}")

    elif args.direction == "from_sheet":
        result = sync.sync_from_sheet()
        if result["approved"] + result["skipped"] > 0:
            sync.sync_to_sheet()
        sync.sync_dashboard()
        print(f"✅ スプシ→キュー同期完了:")
        print(f"   承認: {result['approved']}件")
        print(f"   スキップ: {result['skipped']}件")
        print(f"   変更なし: {result['unchanged']}件")
        if result["errors"]:
            print(f"   エラー: {result['errors']}")

    elif args.direction == "full":
        result = sync.full_sync()
        print(f"✅ 完全同期完了:")
        print(f"   スプシ→キュー: 承認{result['from_sheet']['approved']}件, スキップ{result['from_sheet']['skipped']}件")
        print(f"   キュー→スプシ: {result['to_sheet']['synced']}件同期")
        print(f"   ダッシュボード: 更新済み")

    # Discord通知
    if not args.quiet:
        try:
            from src.notify.discord_notifier import DiscordNotifier
            webhook = config.discord_webhook_account or config.discord_webhook_general
            if webhook:
                notifier = DiscordNotifier(webhook)
                notifier.send(content=f"🔄 キュー同期完了（{args.direction}）")
        except Exception:
            pass


def cmd_sync_settings(args):
    """スプレッドシート設定シートから設定を読み込み表示"""
    from src.sheets.sheets_client import SheetsClient
    from src.sheets.queue_sync import QueueSync

    config = Config(f"account_{args.account}")
    print("⚙️ 設定読み込み中...")

    try:
        sheets = SheetsClient(config)
    except ValueError as e:
        print(f"❌ {e}")
        return

    sync = QueueSync(sheets)
    settings = sync.read_settings()

    print(f"\n{'='*40}")
    print("📋 スプレッドシート設定:")
    print(f"{'='*40}")
    for key, value in settings.items():
        print(f"  {key}: {value}")
    print(f"{'='*40}")


def cmd_export_dashboard(args):
    """ダッシュボード用JSONデータをエクスポート"""
    from src.collect.queue_manager import QueueManager

    queue = QueueManager()
    all_pending = queue.get_all_pending()
    processed = queue._load(queue._processed_file)
    stats = queue.stats()

    # メトリクスファイル読み込み
    metrics_dir = PROJECT_ROOT / "data" / "metrics"
    recent_metrics = []
    if metrics_dir.exists():
        metric_files = sorted(metrics_dir.glob("*.json"), reverse=True)[:7]
        for mf in metric_files:
            try:
                with open(mf, encoding="utf-8") as f:
                    recent_metrics.append(json.load(f))
            except Exception:
                pass

    # 直近の投稿履歴（processed から最新30件）
    recent_posted = sorted(
        [p for p in processed if p.get("posted_at")],
        key=lambda x: x.get("posted_at", ""),
        reverse=True,
    )[:30]

    # PDCA分析データ
    pdca_insights = {}
    try:
        feedback_stats = queue.get_feedback_stats()
        if feedback_stats:
            pdca_insights = {
                "approval_rate": feedback_stats.get("approval_rate", 0),
                "total_decisions": feedback_stats.get("total", 0),
                "by_source": feedback_stats.get("by_source", {}),
                "by_topic": feedback_stats.get("by_topic", {}),
                "by_reason": feedback_stats.get("by_reason", {}),
            }
    except Exception:
        pass

    # プリファレンス設定
    preferences_summary = {}
    try:
        from src.collect.preference_scorer import PreferenceScorer
        scorer = PreferenceScorer()
        prefs = scorer.preferences
        preferences_summary = {
            "weekly_focus": prefs.get("weekly_focus", {}).get("directive", ""),
            "preferred_topics": prefs.get("topic_preferences", {}).get("preferred", []),
            "avoid_topics": prefs.get("topic_preferences", {}).get("avoid", []),
            "boosted_accounts": prefs.get("account_overrides", {}).get("boosted", []),
            "version": prefs.get("version", 1),
            "updated_at": prefs.get("updated_at", ""),
        }
    except Exception:
        pass

    dashboard_data = {
        "updated_at": datetime.now().isoformat(),
        "stats": stats,
        "queue": all_pending,
        "recent_posted": recent_posted,
        "metrics": recent_metrics,
        "pdca_insights": pdca_insights,
        "preferences": preferences_summary,
    }

    output_path = PROJECT_ROOT / "public" / "dashboard-data.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dashboard_data, f, ensure_ascii=False, indent=2)

    print(f"📊 ダッシュボードデータをエクスポート: {output_path}")
    print(f"   キュー: {len(all_pending)}件 / 投稿済み: {len(recent_posted)}件")


def cmd_preferences(args):
    """選定プリファレンスの表示・同期"""
    from src.collect.preference_scorer import PreferenceScorer

    config = Config(f"account_{args.account}")

    if args.sync:
        # スプレッドシートからプリファレンスを同期
        print("🔄 プリファレンスをスプレッドシートから同期中...")
        try:
            from src.sheets.sheets_client import SheetsClient
            from src.sheets.queue_sync import QueueSync
            sheets = SheetsClient(config)
            sync = QueueSync(sheets)
            result = sync.sync_preferences()
            if result["updated_keys"]:
                print(f"✅ 更新: {', '.join(result['updated_keys'])}")
            else:
                print("✅ 変更なし")
        except Exception as e:
            print(f"❌ 同期エラー: {e}")
        return

    # デフォルト: 現在のプリファレンスを表示
    scorer = PreferenceScorer()
    prefs = scorer.preferences

    print(f"\n{'='*50}")
    print("🎯 選定プリファレンス設定")
    print(f"{'='*50}")

    # Weekly Focus
    wf = prefs.get("weekly_focus", {})
    print(f"\n📌 今週のフォーカス:")
    print(f"   テーマ: {wf.get('directive', '（未設定）') or '（未設定）'}")
    print(f"   キーワード: {', '.join(wf.get('focus_keywords', [])) or '（なし）'}")
    print(f"   アカウント: {', '.join(wf.get('focus_accounts', [])) or '（なし）'}")

    # Topics
    tp = prefs.get("topic_preferences", {})
    print(f"\n📋 トピック:")
    print(f"   優先: {', '.join(tp.get('preferred', []))}")
    print(f"   回避: {', '.join(tp.get('avoid', []))}")

    # Accounts
    ao = prefs.get("account_overrides", {})
    print(f"\n👤 アカウント:")
    print(f"   優先: {', '.join(ao.get('boosted', [])) or '（なし）'}")
    print(f"   ブロック: {', '.join(ao.get('blocked', [])) or '（なし）'}")

    # Keywords
    kw = prefs.get("keyword_weights", {})
    print(f"\n🔑 キーワード重み:")
    for k, v in sorted(kw.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"   {k}: {v}")

    print(f"\n   更新日: {prefs.get('updated_at', '—')}")
    print(f"   更新者: {prefs.get('updated_by', '—')}")
    print(f"   バージョン: {prefs.get('version', 1)}")
    print(f"{'='*50}")


def cmd_selection_pdca(args):
    """選定PDCAの実行（分析→調整→レポート）"""
    from src.pdca.preference_updater import PreferenceUpdater

    print("🎯 選定PDCA実行中...")

    updater = PreferenceUpdater()

    # 1. 分析
    print("\n── STEP 1: フィードバック分析 ──")
    analysis = updater.analyze_feedback()

    if analysis["total_decisions"] == 0:
        print("  📭 フィードバックデータがありません。")
        print("  💡 ツイートの承認/スキップ操作を行ってからお試しください。")
        return

    print(f"  判断数: {analysis['total_decisions']}件")
    print(f"  承認率: {analysis['approval_rate']*100:.1f}%")

    if analysis["account_recommendations"]["promote"]:
        print(f"\n  ✅ 高承認率アカウント:")
        for p in analysis["account_recommendations"]["promote"][:5]:
            print(f"     @{p['username']}: {p['rate']*100:.0f}% ({p['count']}件)")

    if analysis["account_recommendations"]["demote"]:
        print(f"\n  ⚠️ 低承認率アカウント:")
        for d in analysis["account_recommendations"]["demote"][:5]:
            print(f"     @{d['username']}: {d['rate']*100:.0f}% ({d['count']}件)")

    if analysis["top_skip_reasons"]:
        reason_labels = {
            "topic_mismatch": "トピック不一致",
            "source_untrusted": "ソース不適切",
            "too_old": "古すぎる",
            "low_quality": "品質不足",
            "off_brand": "ブランド不適合",
            "other": "その他",
        }
        print(f"\n  📋 スキップ理由:")
        for sr in analysis["top_skip_reasons"][:5]:
            label = reason_labels.get(sr["reason"], sr["reason"])
            print(f"     {label}: {sr['count']}件")

    # 2. 自動調整
    if args.auto_adjust:
        print("\n── STEP 2: 自動調整 ──")
        result = updater.auto_update(dry_run=args.dry_run)
        if result["changes"]:
            for change in result["changes"]:
                print(f"  🔄 {change}")
            if args.dry_run:
                print(f"\n  🔒 ドライラン: 変更は保存されません")
            else:
                print(f"\n  ✅ {result['summary']}")
        else:
            print(f"  ℹ️ {result['summary']}")
    else:
        print("\n💡 --auto-adjust フラグで自動調整を実行できます")

    # 3. レポート生成
    print("\n── STEP 3: レポート ──")
    report = updater.generate_report()
    print(report)

    # Discord通知
    if not args.dry_run:
        try:
            config = Config(f"account_{args.account}")
            from src.notify.discord_notifier import DiscordNotifier
            webhook = config.discord_webhook_metrics or config.discord_webhook_general
            if webhook:
                notifier = DiscordNotifier(webhook)
                notifier.send(content=report)
                print("\n📨 Discord通知を送信しました")
        except Exception as e:
            print(f"⚠️ Discord通知エラー: {e}")


def cmd_sync_from_firebase(args):
    """Firestore（ダッシュボード操作）→ ローカルJSON同期"""
    import os
    from src.firestore.firestore_client import FirestoreClient
    from src.firestore.firebase_sync import FirebaseSync

    quiet = getattr(args, "quiet", False)

    if not quiet:
        print("🔥 Firebase同期開始（ダッシュボード → バックエンド）")

    try:
        fc = FirestoreClient()
        fb_sync = FirebaseSync(fc)
    except Exception as e:
        if not quiet:
            print(f"❌ Firebase初期化エラー: {e}")
        return

    queue_only = getattr(args, "queue_only", False)
    prefs_only = getattr(args, "prefs_only", False)

    # キュー決定の同期
    if not prefs_only:
        try:
            q_result = fb_sync.sync_queue_decisions()
            if not quiet:
                total = q_result["approved"] + q_result["skipped"]
                if total > 0:
                    print(f"  ✅ キュー同期: 承認{q_result['approved']}件, スキップ{q_result['skipped']}件")
                    if q_result["not_found"]:
                        print(f"  ⚠️ 見つからなかった決定: {q_result['not_found']}件")
                else:
                    print("  📭 キュー決定: 新規なし")
            if q_result["errors"] and not quiet:
                for err in q_result["errors"]:
                    print(f"  ❌ {err}")
        except Exception as e:
            if not quiet:
                print(f"  ⚠️ キュー同期エラー: {e}")

    # プリファレンスの同期
    if not queue_only:
        uid = getattr(args, "uid", "") or os.getenv("FIREBASE_UID", "")
        if uid:
            try:
                p_result = fb_sync.sync_selection_preferences(uid)
                if not quiet:
                    if p_result["updated_keys"]:
                        print(f"  🎯 プリファレンス同期: {', '.join(p_result['updated_keys'])}")
                    else:
                        print("  📭 プリファレンス: 変更なし")
            except Exception as e:
                if not quiet:
                    print(f"  ⚠️ プリファレンス同期エラー: {e}")
        elif not quiet:
            print("  ⚠️ プリファレンス同期スキップ（--uid または FIREBASE_UID 未設定）")

    if not quiet:
        print("🔥 Firebase同期完了")


def cmd_process_operations(args):
    """ダッシュボードからの操作リクエストを処理"""
    import os
    import subprocess
    import sys
    from src.firestore.firestore_client import FirestoreClient

    print("🔄 ダッシュボード操作リクエストを確認中...")

    try:
        fc = FirestoreClient()
    except Exception as e:
        print(f"❌ Firebase初期化エラー: {e}")
        return

    # 全ユーザーの未処理リクエストを走査（マルチユーザー対応）
    pending = fc.get_pending_operations()

    if not pending:
        print("📭 未処理のリクエストはありません")
        return

    print(f"📋 {len(pending)}件のリクエストを処理します")

    for op in pending:
        cmd = op.get("command", "")
        doc_id = op["id"]
        op_uid = op.get("uid", "")
        print(f"\n▶ 実行中: {cmd} (id: {doc_id}, user: {op_uid})")

        fc.update_operation_status(doc_id, "running", uid=op_uid)

        # ユーザー別のX API認証情報をFirestoreから取得し、subprocess環境変数に注入
        sub_env = os.environ.copy()
        if op_uid:
            user_creds = fc.get_user_x_credentials(op_uid)
            if user_creds:
                cred_map = {
                    "X_API_KEY": user_creds.get("api_key", ""),
                    "X_API_SECRET": user_creds.get("api_secret", ""),
                    "X_ACCOUNT_1_ACCESS_TOKEN": user_creds.get("access_token", ""),
                    "X_ACCOUNT_1_ACCESS_SECRET": user_creds.get("access_token_secret", ""),
                    "TWITTER_BEARER_TOKEN": user_creds.get("bearer_token", ""),
                }
                # 空でない値のみ上書き（Firestore未設定の項目はGitHub Secretsにフォールバック）
                for k, v in cred_map.items():
                    if v:
                        sub_env[k] = v
                print(f"  🔑 ユーザー {op_uid} のX API認証情報をFirestoreから取得")
            else:
                print(f"  ⚠️ ユーザー {op_uid} のAPI設定がFirestoreにありません。GitHub Secretsを使用")

            # Gemini/Discord もユーザー設定があれば上書き
            user_keys = fc.get_api_keys(op_uid)
            if user_keys:
                if user_keys.get("gemini_api_key"):
                    sub_env["GEMINI_API_KEY"] = user_keys["gemini_api_key"]
                if user_keys.get("discord_webhook_url"):
                    sub_env["DISCORD_WEBHOOK_ACCOUNT_1"] = user_keys["discord_webhook_url"]

        try:
            if cmd == "add-tweet":
                tweet_url = op.get("tweet_url", "")
                if tweet_url:
                    result = subprocess.run(
                        [sys.executable, "tools/add_tweet.py", tweet_url],
                        capture_output=True, text=True, timeout=60,
                        env=sub_env,
                    )
                    print(result.stdout)
                    if result.returncode != 0:
                        err_msg = (result.stderr or result.stdout or "add_tweet failed").strip()
                        raise Exception(err_msg[-500:])
                    # 自動承認
                    subprocess.run(
                        [sys.executable, "tools/add_tweet.py", "--approve-all"],
                        capture_output=True, text=True, timeout=30,
                        env=sub_env,
                    )
                    fc.update_operation_status(doc_id, "completed", f"Added: {tweet_url}", uid=op_uid)
                else:
                    fc.update_operation_status(doc_id, "failed", "No tweet URL provided", uid=op_uid)

            elif cmd in ("collect", "curate", "curate-post", "export-dashboard"):
                sub_args = [sys.executable, "-m", "src.main", cmd, "--account", "1"]
                if cmd == "collect":
                    sub_args.extend(["--auto-approve", "--min-likes", "500"])
                result = subprocess.run(
                    sub_args,
                    capture_output=True, text=True, timeout=300,
                    env=sub_env,
                )
                print(result.stdout)
                if result.returncode != 0:
                    err_msg = (result.stderr or result.stdout or f"{cmd} failed").strip()
                    print(f"  stderr: {err_msg}")
                    raise Exception(err_msg[-500:])
                fc.update_operation_status(doc_id, "completed", f"{cmd} succeeded", uid=op_uid)
            else:
                fc.update_operation_status(doc_id, "failed", f"Unknown command: {cmd}", uid=op_uid)

        except subprocess.TimeoutExpired as e:
            print(f"❌ タイムアウト: {cmd}")
            fc.update_operation_status(doc_id, "failed", f"Timeout after 300s: {cmd}", uid=op_uid)
        except Exception as e:
            print(f"❌ エラー: {e}")
            fc.update_operation_status(doc_id, "failed", str(e)[:200], uid=op_uid)

    print("\n✅ 操作リクエスト処理完了")


def cmd_analyze_persona(args):
    """Xアカウントの文体を分析してペルソナプロファイルを生成"""
    from src.analyze.persona_analyzer import PersonaAnalyzer
    from src.collect.x_api_client import XAPIClient, XAPIError

    config = Config(f"account_{args.account}")
    username = args.username or config.account_handle.lstrip("@")

    print(f"🔍 ペルソナ分析開始 — @{username}")

    # ツイート取得（X API v2 or ファイルから）
    tweets_text = []

    if args.file:
        # ファイルからツイートを読み込む（1行1ツイート or JSON）
        file_path = Path(args.file)
        if file_path.suffix == ".json":
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    tweets_text = [t.get("text", t) if isinstance(t, dict) else str(t) for t in data]
                else:
                    tweets_text = [data.get("text", str(data))]
        else:
            with open(file_path, "r", encoding="utf-8") as f:
                tweets_text = [line.strip() for line in f if line.strip()]
        print(f"📄 ファイルから{len(tweets_text)}件のツイートを読み込み")
    else:
        # X API v2で取得
        import os
        bearer_token = os.getenv("TWITTER_BEARER_TOKEN", "")
        if not bearer_token:
            print("❌ TWITTER_BEARER_TOKEN が設定されていません。")
            print("   代替: --file オプションでツイートファイルを指定してください。")
            return

        try:
            client = XAPIClient(bearer_token)
        except ValueError as e:
            print(f"❌ {e}")
            return

        print(f"📡 @{username} のツイートをX API v2で取得中...")

        try:
            raw_tweets = client.get_user_tweets(username, max_results=args.count)
            tweets_text = [t.get("text", "") for t in raw_tweets if t.get("text")]
            print(f"📥 {len(tweets_text)}件のツイートを取得")
        except XAPIError as e:
            print(f"❌ ツイート取得エラー: {e}")
            return

    if not tweets_text:
        print("❌ 分析対象のツイートがありません。")
        return

    # 分析実行
    analyzer = PersonaAnalyzer(config)
    profile = analyzer.analyze_account(
        tweets=tweets_text,
        username=username,
    )

    # 結果の保存
    output_dir = PROJECT_ROOT / "data" / "persona"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"account_{args.account}_persona.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)

    # プロンプト注入テキストも保存
    prompt_path = output_dir / f"account_{args.account}_persona_prompt.md"
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(profile.to_prompt_injection())

    print(f"\n✅ ペルソナ分析完了")
    print(f"   分析ツイート数: {profile.tweet_count_analyzed}")
    print(f"   一人称: {profile.first_person or '不明'}")
    print(f"   トーン: {profile.tone or '（AI分析なし）'}")
    print(f"   敬語レベル: {profile.formality_level}")
    print(f"   絵文字使用: {'あり' if profile.uses_emoji else 'なし'}")
    print(f"   平均ツイート長: {profile.avg_tweet_length:.0f}文字")

    if profile.catchphrases:
        print(f"   口癖: {', '.join(profile.catchphrases[:5])}")
    if profile.sentence_endings:
        print(f"   文末パターン: {', '.join(profile.sentence_endings[:5])}")

    print(f"\n📁 保存先:")
    print(f"   プロファイル: {output_path}")
    print(f"   プロンプト: {prompt_path}")


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

    # collect (パターンB)
    collect_parser = add_account_arg(subparsers.add_parser("collect", help="バズツイートを自動収集（X API v2）"))
    collect_parser.add_argument("--dry-run", action="store_true", help="ドライラン（キューに追加しない）")
    collect_parser.add_argument("--auto-approve", action="store_true", help="収集したツイートを自動承認")
    collect_parser.add_argument("--min-likes", type=int, default=None, help="最低いいね数（デフォルト: 設定ファイルの値）")
    collect_parser.add_argument("--max-tweets", type=int, default=50, help="最大取得件数（デフォルト: 50）")

    # metrics
    metrics_parser = add_account_arg(subparsers.add_parser("metrics", help="メトリクス収集 & Discord通知"))
    metrics_parser.add_argument("--days", type=int, default=7, help="集計期間（日数、デフォルト: 7）")

    # weekly-pdca
    pdca_parser = add_account_arg(subparsers.add_parser("weekly-pdca", help="週次PDCAレポート生成 & Discord通知"))
    pdca_parser.add_argument("--days", type=int, default=7, help="集計期間（日数、デフォルト: 7）")

    # import-urls (パターンA: スプシ→キュー)
    import_parser = add_account_arg(subparsers.add_parser("import-urls", help="スプレッドシートからURL一括インポート"))
    import_parser.add_argument("--auto-approve", action="store_true", help="インポートと同時に承認")

    # setup-sheets (初回セットアップ)
    add_account_arg(subparsers.add_parser("setup-sheets", help="スプレッドシートの初期セットアップ"))

    # sync-queue (パターンB: キュー同期)
    sync_parser = add_account_arg(
        subparsers.add_parser("sync-queue", help="キュー <-> スプレッドシート同期")
    )
    sync_parser.add_argument(
        "--direction", "-d",
        choices=["to_sheet", "from_sheet", "full"],
        default="full",
        help="同期方向（default: full）"
    )
    sync_parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Discord通知を抑制"
    )

    # sync-settings
    add_account_arg(
        subparsers.add_parser("sync-settings", help="スプレッドシートから設定を読み込み")
    )

    # export-dashboard (パターンB: ダッシュボードデータ出力)
    add_account_arg(
        subparsers.add_parser("export-dashboard", help="ダッシュボード用JSONデータをエクスポート")
    )

    # preferences (選定プリファレンス管理)
    pref_parser = add_account_arg(
        subparsers.add_parser("preferences", help="選定プリファレンスの表示・同期")
    )
    pref_parser.add_argument("--sync", action="store_true", help="スプレッドシートからプリファレンスを同期")

    # selection-pdca (選定PDCA)
    sel_pdca_parser = add_account_arg(
        subparsers.add_parser("selection-pdca", help="選定PDCAの実行（分析→調整→レポート）")
    )
    sel_pdca_parser.add_argument("--auto-adjust", action="store_true", help="分析結果に基づいて自動調整")
    sel_pdca_parser.add_argument("--dry-run", action="store_true", help="ドライラン（変更を保存しない）")

    # sync-from-firebase (Firestore → ローカルJSON同期)
    fb_sync_parser = add_account_arg(
        subparsers.add_parser("sync-from-firebase", help="Firestore（ダッシュボード操作）→ ローカルJSON同期")
    )
    fb_sync_parser.add_argument("--uid", type=str, default="", help="対象ユーザーUID（デフォルト: FIREBASE_UID環境変数）")
    fb_sync_parser.add_argument("--queue-only", action="store_true", help="キュー決定のみ同期")
    fb_sync_parser.add_argument("--prefs-only", action="store_true", help="プリファレンスのみ同期")
    fb_sync_parser.add_argument("--quiet", action="store_true", help="出力抑制（GitHub Actions用）")

    # process-operations (ダッシュボード操作リクエスト処理)
    op_parser = add_account_arg(
        subparsers.add_parser("process-operations", help="ダッシュボードからの操作リクエストを処理")
    )

    # analyze-persona (Xアカウントの文体分析)
    persona_parser = add_account_arg(
        subparsers.add_parser("analyze-persona", help="Xアカウントの文体を分析してペルソナプロファイル生成")
    )
    persona_parser.add_argument("--username", type=str, default="", help="分析対象のXユーザー名（省略時はアカウント設定のhandle）")
    persona_parser.add_argument("--file", type=str, default="", help="ツイートファイルパス（JSON or テキスト）")
    persona_parser.add_argument("--count", type=int, default=100, help="取得ツイート数（API使用時）")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "generate": cmd_generate,
        "post": cmd_post,
        "curate": cmd_curate,
        "curate-post": cmd_curate_post,
        "collect": cmd_collect,
        "notify-test": cmd_notify_test,
        "metrics": cmd_metrics,
        "weekly-pdca": cmd_weekly_pdca,
        "import-urls": cmd_import_urls,
        "setup-sheets": cmd_setup_sheets,
        "sync-queue": cmd_sync_queue,
        "sync-settings": cmd_sync_settings,
        "export-dashboard": cmd_export_dashboard,
        "analyze-persona": cmd_analyze_persona,
        "preferences": cmd_preferences,
        "selection-pdca": cmd_selection_pdca,
        "sync-from-firebase": cmd_sync_from_firebase,
        "process-operations": cmd_process_operations,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
