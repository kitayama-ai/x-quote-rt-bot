"""
X Auto Post System — 自動バズツイート収集（パターンB）

X API v2 (tweepy) を使って、target_accounts.json に登録された
海外AIアカウントのバズツイートを自動収集し、キューに追加する。

Usage:
    python -m src.main collect --account 1 [--dry-run]
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.collect.x_api_client import XAPIClient, XAPIError
from src.collect.tweet_parser import TweetParser, ParsedTweet
from src.collect.queue_manager import QueueManager
from src.collect.preference_scorer import PreferenceScorer
from src.config import PROJECT_ROOT

JST = ZoneInfo("Asia/Tokyo")

# 1回の検索クエリに含めるアカウント数の上限
# OR結合が多すぎるとAPI側で弾かれる場合がある
MAX_ACCOUNTS_PER_QUERY = 8


class AutoCollector:
    """バズツイートを自動収集してキューに追加"""

    def __init__(
        self,
        bearer_token: str = "",
        queue: QueueManager | None = None,
    ):
        self.client = XAPIClient(bearer_token=bearer_token)
        self.queue = queue or QueueManager()
        self.preference_scorer = PreferenceScorer()
        self._load_config()

    def _load_config(self):
        """設定ファイル読み込み"""
        # ターゲットアカウント
        path = PROJECT_ROOT / "config" / "target_accounts.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.target_accounts = data.get("accounts", [])
        self.keywords = data.get("keywords", [])

        # 引用RTルール（バズ閾値）
        rules_path = PROJECT_ROOT / "config" / "quote_rt_rules.json"
        with open(rules_path, "r", encoding="utf-8") as f:
            rules = json.load(f)
        self.buzz_thresholds = rules.get("buzz_thresholds", {})

    def collect(
        self,
        min_likes: int | None = None,
        lang: str | None = None,
        max_age_hours: int | None = None,
        max_tweets: int = 50,
        auto_approve: bool = False,
        dry_run: bool = False,
    ) -> dict:
        """
        バズツイートを収集してキューに追加

        Args:
            min_likes: 最低いいね数（None=設定ファイルから）
            lang: 言語フィルタ
            max_age_hours: 最大ツイート経過時間
            max_tweets: 最大取得件数
            auto_approve: 自動承認するか
            dry_run: True=キューに追加しない

        Returns:
            {"fetched", "filtered", "added", "skipped_dup", "tweets"}
        """
        _min_likes = min_likes or self.buzz_thresholds.get("likes_min", 500)
        _lang = lang or self.buzz_thresholds.get("lang", ["en"])[0]
        _max_age = max_age_hours or self.buzz_thresholds.get("age_max_hours", 48)

        print(f"🔍 収集設定: min_likes={_min_likes}, lang={_lang}, max_age={_max_age}h")

        # ── STEP 1: API検索 ──────────────────────────────────────────
        raw_tweets = self._fetch_tweets(
            min_likes=_min_likes,
            lang=_lang,
            max_tweets=max_tweets,
        )
        print(f"📥 API取得: {len(raw_tweets)}件")

        # ── STEP 2: フィルタリング ────────────────────────────────────
        filtered = self._filter_tweets(
            raw_tweets,
            min_likes=_min_likes,
            max_age_hours=_max_age,
        )
        print(f"🔎 フィルタ後: {len(filtered)}件 ({len(raw_tweets) - len(filtered)}件除外)")

        # ── STEP 3: ParsedTweetに変換 ────────────────────────────────
        parsed_tweets = []
        for tweet_data in filtered:
            try:
                parsed = TweetParser.from_api_data(tweet_data, source="x_api_v2")
                parsed_tweets.append(parsed)
            except Exception as e:
                print(f"  ⚠️ パースエラー: {e}")

        # ── STEP 3.5: プリファレンススコアリング ─────────────────────
        for tweet in parsed_tweets:
            pref_result = self.preference_scorer.score(
                tweet_text=tweet.text,
                author_username=tweet.author_username,
            )
            tweet.preference_match_score = pref_result["preference_score"]
            tweet.matched_topics = pref_result["matched_topics"]
            tweet.matched_keywords = pref_result["matched_keywords"]

        # プリファレンスでブロックされたツイートを除外
        before_pref = len(parsed_tweets)
        parsed_tweets = [
            t for t in parsed_tweets
            if not self.preference_scorer.is_account_blocked(t.author_username)
        ]
        if before_pref != len(parsed_tweets):
            print(f"🚫 ブロックアカウント除外: {before_pref - len(parsed_tweets)}件")

        # ブレンドスコア（エンゲージメント × プリファレンス）で再ソート
        parsed_tweets.sort(
            key=lambda t: (t.likes + t.retweets * 3) * max(t.preference_match_score, 0.1),
            reverse=True,
        )

        pref_matched = sum(1 for t in parsed_tweets if t.preference_match_score > 1.0)
        print(f"🎯 プリファレンスマッチ: {pref_matched}/{len(parsed_tweets)}件")

        # ── STEP 4: キューに追加 ──────────────────────────────────────
        added = 0
        skipped_dup = 0

        if not dry_run:
            for tweet in parsed_tweets:
                if self.queue.add(tweet):
                    added += 1
                    if auto_approve:
                        self.queue.approve(tweet.tweet_id)
                else:
                    skipped_dup += 1
        else:
            added = len(parsed_tweets)

        return {
            "fetched": len(raw_tweets),
            "filtered": len(filtered),
            "added": added,
            "skipped_dup": skipped_dup,
            "tweets": parsed_tweets,
        }

    def _fetch_tweets(
        self,
        min_likes: int,
        lang: str,
        max_tweets: int,
    ) -> list[dict]:
        """ターゲットアカウントからバズツイートを検索"""
        all_tweets = []

        # アカウントをpriority順にソート（high優先）
        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_accounts = sorted(
            self.target_accounts,
            key=lambda a: priority_order.get(a.get("priority", "medium"), 1),
        )

        # アカウントをチャンクに分割してクエリ実行
        usernames = [a["username"] for a in sorted_accounts]
        chunks = [
            usernames[i : i + MAX_ACCOUNTS_PER_QUERY]
            for i in range(0, len(usernames), MAX_ACCOUNTS_PER_QUERY)
        ]

        for chunk in chunks:
            query = self.client.build_search_query(
                accounts=chunk,
                min_likes=min_likes,
                lang=lang,
            )
            print(f"  🔍 検索: {query[:80]}...")

            try:
                tweets = self.client.search_tweets(
                    query=query,
                    max_results=max_tweets,
                )
                all_tweets.extend(tweets)
                print(f"     → {len(tweets)}件取得")
            except XAPIError as e:
                print(f"     ❌ APIエラー: {e}")

        # キーワード検索（アカウント検索で十分取れなかった場合の補完）
        if len(all_tweets) < max_tweets // 2 and self.keywords:
            query = self.client.build_search_query(
                keywords=self.keywords[:5],
                min_likes=min_likes,
                lang=lang,
            )
            print(f"  🔍 キーワード検索: {query[:80]}...")

            try:
                tweets = self.client.search_tweets(
                    query=query,
                    max_results=max_tweets // 2,
                )
                all_tweets.extend(tweets)
                print(f"     → {len(tweets)}件取得")
            except XAPIError as e:
                print(f"     ❌ APIエラー: {e}")

        # 重複排除（同じtweet_idが複数クエリで取れる場合）
        seen_ids = set()
        unique = []
        for t in all_tweets:
            tid = str(t.get("id_str", t.get("id", "")))
            if tid and tid not in seen_ids:
                seen_ids.add(tid)
                unique.append(t)

        return unique

    def _filter_tweets(
        self,
        tweets: list[dict],
        min_likes: int,
        max_age_hours: int,
    ) -> list[dict]:
        """ツイートをフィルタリング"""
        now = datetime.now(JST)
        cutoff = now - timedelta(hours=max_age_hours)
        filtered = []

        # キューにある既存ツイートIDを取得（重複防止）
        existing_ids = set()
        try:
            all_pending = self.queue.get_all_pending()
            existing_ids = {item["tweet_id"] for item in all_pending}
            processed = self.queue._load(self.queue._processed_file)
            existing_ids.update(item["tweet_id"] for item in processed)
        except Exception:
            pass

        # 同一ソース制限: 今日すでに追加済みのソース
        today_sources = set()
        try:
            today_str = now.date().isoformat()
            for item in all_pending:
                added_at = item.get("added_at", "")
                if added_at.startswith(today_str):
                    today_sources.add(item.get("author_username", ""))
        except Exception:
            pass

        for tweet in tweets:
            tid = str(tweet.get("id_str", tweet.get("id", "")))

            # 既存チェック
            if tid in existing_ids:
                continue

            # いいね数チェック
            likes = tweet.get("favorite_count", tweet.get("like_count", 0))
            if likes < min_likes:
                continue

            # 言語チェック（SocialDataはlangフィールドを返す）
            lang = tweet.get("lang", "")
            if lang and lang not in ("en", "und"):
                continue

            # リプライ除外
            if tweet.get("in_reply_to_status_id") or tweet.get("in_reply_to_status_id_str"):
                continue

            # RT除外
            if tweet.get("retweeted_status") or str(tweet.get("full_text", "")).startswith("RT @"):
                continue

            # 同一ソース制限（1日1件まで）
            user = tweet.get("user", {})
            username = user.get("screen_name", "")
            if username in today_sources:
                continue

            # 経過時間チェック（SocialDataの created_at をパース）
            created_at_str = tweet.get("created_at", "")
            if created_at_str:
                try:
                    # "Thu Feb 20 02:14:30 +0000 2026" 形式
                    created_at = datetime.strptime(
                        created_at_str, "%a %b %d %H:%M:%S %z %Y"
                    )
                    if created_at < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass  # パースできない場合はスキップせず通す

            filtered.append(tweet)
            today_sources.add(username)

        # いいね数の降順でソート
        filtered.sort(
            key=lambda t: t.get("favorite_count", t.get("like_count", 0)),
            reverse=True,
        )

        return filtered

    def format_result(self, result: dict) -> str:
        """収集結果をフォーマット"""
        lines = [
            "📊 収集結果:",
            f"  API取得:    {result['fetched']}件",
            f"  フィルタ後: {result['filtered']}件",
            f"  キュー追加: {result['added']}件",
            f"  重複スキップ: {result['skipped_dup']}件",
        ]

        if result["tweets"]:
            lines.append("")
            lines.append("  📝 追加されたツイート:")
            for t in result["tweets"][:10]:
                lines.append(
                    f"    @{t.author_username} ({t.likes:,}❤) "
                    f"{t.text[:50]}..."
                )

        return "\n".join(lines)
