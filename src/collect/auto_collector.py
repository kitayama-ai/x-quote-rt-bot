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

        # 検索設定（verified, min_followers, スパム除外）
        ss = data.get("search_settings", {})
        self.require_verified = ss.get("require_verified", True)
        self.min_followers = ss.get("min_followers", 1000)
        self.excluded_terms = ss.get("excluded_terms", [])

        # 引用RTルール（バズ閾値）
        rules_path = PROJECT_ROOT / "config" / "quote_rt_rules.json"
        with open(rules_path, "r", encoding="utf-8") as f:
            rules = json.load(f)
        self.buzz_thresholds = rules.get("buzz_thresholds", {})

        # ダッシュボード/PDCA からの閾値上書き
        prefs_path = PROJECT_ROOT / "config" / "selection_preferences.json"
        try:
            with open(prefs_path, "r", encoding="utf-8") as f:
                prefs = json.load(f)
            self.threshold_overrides = prefs.get("threshold_overrides", {})
        except (FileNotFoundError, json.JSONDecodeError):
            self.threshold_overrides = {}

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
        # 優先順位: CLI引数 > ダッシュボード設定(threshold_overrides) > quote_rt_rules
        # ※ min_likes=0 を有効にするため `is not None` で判定（0 は falsy なので `or` チェーン不可）
        if min_likes is not None:
            _min_likes = min_likes
        elif self.threshold_overrides.get("min_likes") is not None:
            _min_likes = self.threshold_overrides["min_likes"]
        else:
            _min_likes = self.buzz_thresholds.get("likes_min", 0)

        _lang = lang or self.buzz_thresholds.get("lang", ["en"])[0]

        if max_age_hours is not None:
            _max_age = max_age_hours
        elif self.threshold_overrides.get("max_age_hours") is not None:
            _max_age = self.threshold_overrides["max_age_hours"]
        else:
            _max_age = self.buzz_thresholds.get("age_max_hours", 48)
        # max_tweets: CLI引数がデフォルト(50)ならダッシュボード設定を優先
        _max_tweets = max_tweets
        if max_tweets == 50 and self.threshold_overrides.get("max_tweets"):
            _max_tweets = self.threshold_overrides["max_tweets"]

        print(f"🔍 収集設定: min_likes={_min_likes}, lang={_lang}, max_age={_max_age}h, max_tweets={_max_tweets}")

        # ── STEP 1: API検索 ──────────────────────────────────────────
        raw_tweets = self._fetch_tweets(
            min_likes=_min_likes,
            lang=_lang,
            max_tweets=_max_tweets,
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
        """キーワード検索でバズツイートを収集（sort_order=relevancyで人気順）"""
        all_tweets = []

        if not self.keywords:
            print("  ⚠️ キーワードが未設定です。config/target_accounts.json の keywords を確認してください。")
            return []

        # キーワードを複数グループに分けて検索（1クエリに詰め込みすぎない）
        KEYWORDS_PER_QUERY = 5
        chunks = [
            self.keywords[i : i + KEYWORDS_PER_QUERY]
            for i in range(0, len(self.keywords), KEYWORDS_PER_QUERY)
        ]

        per_chunk = max(max_tweets // len(chunks), 10)

        for chunk in chunks:
            query = self.client.build_search_query(
                keywords=chunk,
                min_likes=min_likes,
                lang=lang,
            )
            print(f"  🔍 キーワード検索: {query[:80]}...")

            try:
                # relevancy（人気順）で検索
                tweets = self.client.search_tweets(
                    query=query,
                    max_results=per_chunk,
                    tweet_type="Top",
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
        """ツイートをフィルタリング（verified + フォロワー数 + スパム除外）"""
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

        # スパム除外ワード（小文字化して比較）
        excluded_lower = [t.lower() for t in self.excluded_terms]

        skipped_reasons = {"dup": 0, "verified": 0, "followers": 0, "spam": 0, "lang": 0, "reply": 0, "rt": 0, "source": 0, "age": 0}

        for tweet in tweets:
            tid = str(tweet.get("id_str", tweet.get("id", "")))

            # 既存チェック
            if tid in existing_ids:
                skipped_reasons["dup"] += 1
                continue

            user = tweet.get("user", {})
            username = user.get("screen_name", "")
            text_lower = tweet.get("full_text", tweet.get("text", "")).lower()

            # ブルーバッジチェック
            if self.require_verified:
                verified = user.get("verified", False)
                if not verified:
                    skipped_reasons["verified"] += 1
                    continue

            # フォロワー数チェック
            followers = user.get("followers_count", 0)
            if followers < self.min_followers:
                skipped_reasons["followers"] += 1
                continue

            # スパムテキスト除外
            if any(term in text_lower for term in excluded_lower):
                skipped_reasons["spam"] += 1
                continue

            # 言語チェック
            lang = tweet.get("lang", "")
            if lang and lang not in ("en", "und"):
                skipped_reasons["lang"] += 1
                continue

            # リプライ除外
            if tweet.get("in_reply_to_status_id") or tweet.get("in_reply_to_status_id_str"):
                skipped_reasons["reply"] += 1
                continue

            # RT除外
            if tweet.get("retweeted_status") or str(tweet.get("full_text", "")).startswith("RT @"):
                skipped_reasons["rt"] += 1
                continue

            # 同一ソース制限（1日1件まで）
            if username in today_sources:
                skipped_reasons["source"] += 1
                continue

            # 経過時間チェック
            created_at_str = tweet.get("created_at", "")
            if created_at_str:
                try:
                    created_at = datetime.strptime(
                        created_at_str, "%a %b %d %H:%M:%S %z %Y"
                    )
                    if created_at < cutoff:
                        skipped_reasons["age"] += 1
                        continue
                except (ValueError, TypeError):
                    pass

            filtered.append(tweet)
            today_sources.add(username)

        # フィルタ理由を表示
        reasons_str = ", ".join(f"{k}={v}" for k, v in skipped_reasons.items() if v > 0)
        if reasons_str:
            print(f"  📊 除外内訳: {reasons_str}")

        # フォロワー数の降順でソート（いいね数が取れないためフォロワー数で代替）
        filtered.sort(
            key=lambda t: t.get("user", {}).get("followers_count", 0),
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
