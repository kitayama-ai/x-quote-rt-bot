"""
X Auto Post System — 自動バズツイート収集

SocialData API（優先）または X API v2（フォールバック）を使って
AI 界隈のバズツイートを自動収集し、キューに追加する。

SocialData API: いいね・RT・インプレッション・ブックマーク全取得可。
X API v2:       public_metrics が 0 で返るため min_likes フィルタ不可。

Usage:
    python -m src.main collect --account 1 [--dry-run]
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.collect.tweet_parser import TweetParser, ParsedTweet
from src.collect.queue_manager import QueueManager
from src.collect.preference_scorer import PreferenceScorer
from src.config import PROJECT_ROOT

logger = logging.getLogger(__name__)
JST = ZoneInfo("Asia/Tokyo")

# 1 クエリに含めるキーワード/アカウント数の上限
_KEYWORDS_PER_QUERY = 5
_MAX_ACCOUNTS_PER_QUERY = 8


class AutoCollector:
    """バズツイートを自動収集してキューに追加する。

    SocialData API キーが設定されている場合はそちらを使用（メトリクス取得可）。
    未設定の場合は X API v2 にフォールバック（メトリクスは 0）。
    """

    def __init__(
        self,
        bearer_token: str = "",
        socialdata_api_key: str = "",
        queue: QueueManager | None = None,
    ) -> None:
        self.queue = queue or QueueManager()
        self.preference_scorer = PreferenceScorer()

        # ── データソース選択 ──
        self._use_socialdata = False
        self._sd_client = None
        self._x_client = None

        sd_key = socialdata_api_key or os.getenv("SOCIALDATA_API_KEY", "")
        if sd_key:
            from src.collect.socialdata_client import SocialDataClient
            self._sd_client = SocialDataClient(api_key=sd_key)
            self._use_socialdata = True
            print("📡 データソース: SocialData API（メトリクス取得可）")
        else:
            from src.collect.x_api_client import XAPIClient
            self._x_client = XAPIClient(bearer_token=bearer_token)
            print("📡 データソース: X API v2（メトリクス取得不可 — SocialData 推奨）")

        self._load_config()

    # ──────────────────────────────────────────────────────────────
    # 設定読み込み
    # ──────────────────────────────────────────────────────────────

    def _load_config(self) -> None:
        """設定ファイル読み込み"""
        # ── target_accounts.json ──
        path = PROJECT_ROOT / "config" / "target_accounts.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.target_accounts: list[dict] = data.get("accounts", [])
        self.keywords: list[str] = data.get("keywords", [])

        ss = data.get("search_settings", {})
        self.require_verified: bool = ss.get("require_verified", False)
        self.min_followers: int = ss.get("min_followers", 1000)
        self.excluded_terms: list[str] = ss.get("excluded_terms", [])

        # ── quote_rt_rules.json ──
        rules_path = PROJECT_ROOT / "config" / "quote_rt_rules.json"
        with open(rules_path, "r", encoding="utf-8") as f:
            rules = json.load(f)
        self.buzz_thresholds: dict = rules.get("buzz_thresholds", {})

        # ── selection_preferences.json（ダッシュボード設定の上書き）──
        prefs_path = PROJECT_ROOT / "config" / "selection_preferences.json"
        try:
            with open(prefs_path, "r", encoding="utf-8") as f:
                prefs = json.load(f)
            self.threshold_overrides: dict = prefs.get("threshold_overrides", {})
        except (FileNotFoundError, json.JSONDecodeError):
            self.threshold_overrides = {}

    # ──────────────────────────────────────────────────────────────
    # Public: collect
    # ──────────────────────────────────────────────────────────────

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
        バズツイートを収集してキューに追加する。

        Args:
            min_likes: 最低いいね数。None の場合は設定ファイルから取得。
                       SocialData 使用時は API レベルで min_faves フィルタ適用。
                       X API v2 使用時は 0 固定（メトリクス取得不可のため）。
            lang: 言語フィルタ（デフォルト: "en"）。
            max_age_hours: 最大ツイート経過時間（デフォルト: 48h）。
            max_tweets: 最大取得件数。
            auto_approve: True の場合、キュー追加時に自動承認。
            dry_run: True の場合、キューに追加しない。

        Returns:
            {"fetched", "filtered", "added", "skipped_dup", "tweets"}
        """
        # ── パラメータ解決（CLI > ダッシュボード > デフォルト）──
        _min_likes = self._resolve_param(
            cli_value=min_likes,
            override_key="min_likes",
            default_key="likes_min",
            fallback=0,
        )
        _lang = lang or self.buzz_thresholds.get("lang", ["en"])[0]
        _max_age = self._resolve_param(
            cli_value=max_age_hours,
            override_key="max_age_hours",
            default_key="age_max_hours",
            fallback=48,
        )
        _max_tweets = self._resolve_param(
            cli_value=max_tweets if max_tweets != 50 else None,
            override_key="max_tweets",
            default_key=None,
            fallback=50,
        )

        print(f"🔍 収集設定: min_likes={_min_likes}, lang={_lang}, "
              f"max_age={_max_age}h, max_tweets={_max_tweets}")

        # ── STEP 1: API 検索 ──
        raw_tweets = self._fetch_tweets(
            min_likes=_min_likes,
            lang=_lang,
            max_tweets=_max_tweets,
        )
        print(f"📥 API取得: {len(raw_tweets)}件")

        # ── STEP 2: フィルタリング ──
        filtered = self._filter_tweets(
            raw_tweets,
            min_likes=_min_likes,
            max_age_hours=_max_age,
        )
        print(f"🔎 フィルタ後: {len(filtered)}件 ({len(raw_tweets) - len(filtered)}件除外)")

        # ── STEP 3: ParsedTweet 変換 ──
        source_name = "socialdata" if self._use_socialdata else "x_api_v2"
        parsed_tweets: list[ParsedTweet] = []
        for tweet_data in filtered:
            try:
                parsed = TweetParser.from_api_data(tweet_data, source=source_name)
                parsed_tweets.append(parsed)
            except Exception as exc:
                logger.warning("パースエラー: %s", exc)

        # ── STEP 3.5: プリファレンススコアリング ──
        for tweet in parsed_tweets:
            pref_result = self.preference_scorer.score(
                tweet_text=tweet.text,
                author_username=tweet.author_username,
            )
            tweet.preference_match_score = pref_result["preference_score"]
            tweet.matched_topics = pref_result["matched_topics"]
            tweet.matched_keywords = pref_result["matched_keywords"]

        # ブロックアカウント除外
        before_block = len(parsed_tweets)
        parsed_tweets = [
            t for t in parsed_tweets
            if not self.preference_scorer.is_account_blocked(t.author_username)
        ]
        blocked_count = before_block - len(parsed_tweets)
        if blocked_count > 0:
            print(f"🚫 ブロックアカウント除外: {blocked_count}件")

        # ブレンドスコア（エンゲージメント × プリファレンス）で再ソート
        parsed_tweets.sort(
            key=lambda t: (t.likes + t.retweets * 3) * max(t.preference_match_score, 0.1),
            reverse=True,
        )

        pref_matched = sum(1 for t in parsed_tweets if t.preference_match_score > 1.0)
        print(f"🎯 プリファレンスマッチ: {pref_matched}/{len(parsed_tweets)}件")

        # ── STEP 4: キューに追加 ──
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

    # ──────────────────────────────────────────────────────────────
    # Internal: _fetch_tweets
    # ──────────────────────────────────────────────────────────────

    def _fetch_tweets(
        self,
        min_likes: int,
        lang: str,
        max_tweets: int,
    ) -> list[dict]:
        """キーワード検索でバズツイートを収集する。

        SocialData API 使用時: min_faves クエリでバズ判定（API レベル）。
        X API v2 使用時: sort_order=relevancy で人気順取得（メトリクスなし）。
        """
        if self._use_socialdata:
            return self._fetch_via_socialdata(min_likes, lang, max_tweets)
        return self._fetch_via_x_api(min_likes, lang, max_tweets)

    def _fetch_via_socialdata(
        self,
        min_likes: int,
        lang: str,
        max_tweets: int,
    ) -> list[dict]:
        """SocialData API 経由でバズツイートを検索する。"""
        from src.collect.socialdata_client import SocialDataClient, SocialDataError

        assert self._sd_client is not None

        all_tweets: list[dict] = []

        if not self.keywords:
            print("  ⚠️ キーワードが未設定です。")
            return []

        chunks = [
            self.keywords[i : i + _KEYWORDS_PER_QUERY]
            for i in range(0, len(self.keywords), _KEYWORDS_PER_QUERY)
        ]
        per_chunk = max(max_tweets // len(chunks), 10)

        for chunk in chunks:
            query = self._sd_client.build_search_query(
                keywords=chunk,
                min_faves=min_likes,
                lang=lang,
                exclude_replies=True,
                exclude_retweets=True,
            )
            print(f"  🔍 SocialData検索: {query[:80]}...")

            try:
                tweets = self._sd_client.search(
                    query,
                    search_type="Top",
                    max_results=per_chunk,
                )
                all_tweets.extend(tweets)
                print(f"     → {len(tweets)}件取得")
            except SocialDataError as exc:
                print(f"     ❌ SocialDataエラー: {exc}")

        return self._deduplicate(all_tweets)

    def _fetch_via_x_api(
        self,
        min_likes: int,
        lang: str,
        max_tweets: int,
    ) -> list[dict]:
        """X API v2 経由でバズツイートを検索する（フォールバック）。"""
        from src.collect.x_api_client import XAPIError

        assert self._x_client is not None

        all_tweets: list[dict] = []

        if not self.keywords:
            print("  ⚠️ キーワードが未設定です。")
            return []

        chunks = [
            self.keywords[i : i + _KEYWORDS_PER_QUERY]
            for i in range(0, len(self.keywords), _KEYWORDS_PER_QUERY)
        ]
        per_chunk = max(max_tweets // len(chunks), 10)

        for chunk in chunks:
            query = self._x_client.build_search_query(
                keywords=chunk,
                min_likes=min_likes,
                lang=lang,
            )
            print(f"  🔍 X API検索: {query[:80]}...")

            try:
                tweets = self._x_client.search_tweets(
                    query=query,
                    max_results=per_chunk,
                    tweet_type="Top",
                )
                all_tweets.extend(tweets)
                print(f"     → {len(tweets)}件取得")
            except XAPIError as exc:
                print(f"     ❌ X APIエラー: {exc}")

        return self._deduplicate(all_tweets)

    # ──────────────────────────────────────────────────────────────
    # Internal: _filter_tweets
    # ──────────────────────────────────────────────────────────────

    def _filter_tweets(
        self,
        tweets: list[dict],
        min_likes: int,
        max_age_hours: int,
    ) -> list[dict]:
        """ツイートをフィルタリングする。

        フィルタ項目:
            - 重複（キューに既存の tweet_id）
            - いいね数（SocialData 使用時のみ有効）
            - フォロワー数（min_followers 未満を除外）
            - スパムテキスト（excluded_terms に含まれるワード）
            - 言語（en / und 以外を除外）
            - リプライ / RT
            - 同一ソース制限（1著者1日1件）
            - 経過時間（max_age_hours 超過）
        """
        now = datetime.now(JST)
        cutoff = now - timedelta(hours=max_age_hours)

        # ── 既存ツイート ID を収集（重複防止）──
        existing_ids: set[str] = set()
        all_pending: list[dict] = []
        try:
            all_pending = self.queue.get_all_pending()
            existing_ids = {item["tweet_id"] for item in all_pending}
            processed = self.queue._load(self.queue._processed_file)
            existing_ids.update(item["tweet_id"] for item in processed)
        except Exception:
            pass

        # ── 今日すでに追加済みの著者（同一ソース制限）──
        today_sources: set[str] = set()
        try:
            today_str = now.date().isoformat()
            for item in all_pending:
                added_at = item.get("added_at", "")
                if added_at.startswith(today_str):
                    today_sources.add(item.get("author_username", ""))
        except Exception:
            pass

        excluded_lower = [t.lower() for t in self.excluded_terms]

        # フィルタ統計
        stats = {
            "dup": 0, "likes": 0, "followers": 0, "spam": 0,
            "lang": 0, "reply": 0, "rt": 0, "source": 0, "age": 0,
        }

        filtered: list[dict] = []

        for tweet in tweets:
            tid = str(tweet.get("id_str") or tweet.get("id") or "")
            if not tid:
                continue

            # 1. 重複チェック
            if tid in existing_ids:
                stats["dup"] += 1
                continue

            user = tweet.get("user") or tweet.get("author") or {}
            username = str(user.get("screen_name") or user.get("username") or "")
            full_text = str(tweet.get("full_text") or tweet.get("text") or "")
            text_lower = full_text.lower()

            # 2. いいね数チェック (極めて厳格に)
            # favorite_count (v1.1) または like_count (v2) を取得
            likes = tweet.get("favorite_count")
            if likes is None:
                likes = tweet.get("public_metrics", {}).get("like_count")
            if likes is None:
                likes = 0
            
            # SocialData 使用時はいいね数が取れないツイートはバズ判定不能として除外
            if self._use_socialdata and int(likes) < min_likes:
                stats["likes"] += 1
                # デバッグ用に、一定以上のいいねがあるものだけログに理由を出す
                if int(likes) > 0:
                    logger.debug(f"Skipped {tid}: likes={likes} < {min_likes}")
                continue

            # 3. フォロワー数チェック
            followers = int(user.get("followers_count") or user.get("follower_count") or 0)
            if followers < self.min_followers:
                stats["followers"] += 1
                continue

            # 4. スパムテキスト除外
            if any(term in text_lower for term in excluded_lower):
                stats["spam"] += 1
                continue

            # 5. 言語チェック
            tweet_lang = tweet.get("lang", "")
            if tweet_lang and tweet_lang not in ("en", "und"):
                stats["lang"] += 1
                continue

            # 6. リプライ除外
            if (tweet.get("in_reply_to_status_id") or tweet.get("in_reply_to_status_id_str")):
                stats["reply"] += 1
                continue

            # 7. RT 除外
            if (tweet.get("retweeted_status") or tweet.get("quoted_status_id") or full_text.startswith("RT @")):
                stats["rt"] += 1
                continue

            # 8. 同一ソース制限（1著者1日1件）
            if username in today_sources:
                stats["source"] += 1
                continue

            # 9. 経過時間チェック (厳格化: パース失敗なら安全のため除外)
            created_at_str = (
                tweet.get("tweet_created_at") or 
                tweet.get("created_at")
            )
            if not created_at_str:
                stats["age"] += 1
                continue

            created_at = self._parse_created_at(str(created_at_str))
            if created_at is None:
                print(f"  ⚠️ 日付パース失敗のため除外: {created_at_str}")
                stats["age"] += 1
                continue
            
            if created_at < cutoff:
                # 3月1日のツイートなどはここで確実に落とされる
                stats["age"] += 1
                continue

            filtered.append(tweet)
            today_sources.add(username)

        # ── 統計表示 ──
        reasons = ", ".join(f"{k}={v}" for k, v in stats.items() if v > 0)
        if reasons:
            print(f"  📊 除外内訳: {reasons}")

        # ── ソート: いいね数降順（SocialData）/ フォロワー数降順（X API）──
        if self._use_socialdata:
            filtered.sort(
                key=lambda t: t.get("favorite_count", 0),
                reverse=True,
            )
        else:
            filtered.sort(
                key=lambda t: t.get("user", {}).get("followers_count", 0),
                reverse=True,
            )

        return filtered

    # ──────────────────────────────────────────────────────────────
    # Internal: helpers
    # ──────────────────────────────────────────────────────────────

    def _resolve_param(
        self,
        *,
        cli_value: int | None,
        override_key: str,
        default_key: str | None,
        fallback: int,
    ) -> int:
        """パラメータの優先順位を解決する。

        優先順位: CLI 引数 > ダッシュボード設定 > quote_rt_rules > fallback
        """
        if cli_value is not None:
            return cli_value
        if self.threshold_overrides.get(override_key) is not None:
            return int(self.threshold_overrides[override_key])
        if default_key and self.buzz_thresholds.get(default_key) is not None:
            return int(self.buzz_thresholds[default_key])
        return fallback

    @staticmethod
    def _parse_created_at(value: str | None) -> datetime | None:
        """ツイートの作成日時をパースする。

        SocialData 形式: "2026-03-05T12:34:56.000000Z"
        X API v2 形式:   "Thu Mar 05 12:34:56 +0000 2026"
        """
        if not value:
            return None
        
        # SocialData / X API 形式のバリエーション
        formats = (
            "%Y-%m-%dT%H:%M:%S.%fZ",     # SocialData (ISO with microseconds and Z)
            "%Y-%m-%dT%H:%M:%S%z",       # ISO with offset (+0000)
            "%Y-%m-%dT%H:%M:%SZ",       # ISO with Z
            "%a %b %d %H:%M:%S %z %Y",    # X API v1.1 / v2 compatible
        )
        
        clean_value = str(value).strip()
        
        for fmt in formats:
            try:
                dt = datetime.strptime(clean_value, fmt)
                if dt.tzinfo is None:
                    from datetime import timezone
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        
        # fallback: fromisoformat (Python 3.7+)
        try:
            # "Z" を "+00:00" に置換して fromisoformat で読めるようにする
            iso_val = clean_value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso_val)
            if dt.tzinfo is None:
                from datetime import timezone
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            pass

        return None

    @staticmethod
    def _deduplicate(tweets: list[dict]) -> list[dict]:
        """tweet_id で重複を排除する。"""
        seen: set[str] = set()
        unique: list[dict] = []
        for t in tweets:
            tid = str(t.get("id_str", t.get("id", "")))
            if tid and tid not in seen:
                seen.add(tid)
                unique.append(t)
        return unique

    # ──────────────────────────────────────────────────────────────
    # Public: format_result
    # ──────────────────────────────────────────────────────────────

    def format_result(self, result: dict) -> str:
        """収集結果を人間が読みやすい文字列にフォーマットする。"""
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
                    f"    @{t.author_username} ({t.likes:,}❤ {t.retweets:,}🔁) "
                    f"{t.text[:50]}..."
                )

        return "\n".join(lines)
