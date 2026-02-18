"""
X Auto Post System — 安全チェッカー

投稿前に安全性を検証。NGワード、文字数、重複、投稿間隔をチェック。
"""
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher


@dataclass
class SafetyResult:
    """安全チェック結果"""
    is_safe: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        if self.is_safe:
            return "✅ 安全チェック通過"
        return f"❌ 安全チェック不合格: {', '.join(self.violations)}"


class SafetyChecker:
    """投稿の安全性をチェック"""

    def __init__(self, safety_rules: dict):
        self.rules = safety_rules
        self._ng_words = []
        for category_words in safety_rules.get("ng_words", {}).values():
            self._ng_words.extend(category_words)

    def check(
        self,
        text: str,
        past_posts: list[str] | None = None,
        last_post_minutes_ago: int | None = None,
        is_quote_rt: bool = False,
        quote_rt_context: dict | None = None,
    ) -> SafetyResult:
        """
        全安全チェックを実行

        Args:
            text: チェック対象テキスト
            past_posts: 過去の投稿テキストリスト（重複検出用）
            last_post_minutes_ago: 前回投稿からの経過分数
            is_quote_rt: 引用RT投稿かどうか
            quote_rt_context: 引用RT追加情報 {
                "source_username": str,
                "today_same_source_count": int,
                "consecutive_quote_count": int,
            }
        """
        violations = []
        warnings = []

        # 1. NGワードチェック
        ng_found = self._check_ng_words(text)
        if ng_found:
            violations.append(f"NGワード検出: {', '.join(ng_found)}")

        # 2. 文字数チェック
        content_rules = self.rules.get("content_rules", {})
        text_len = len(text.replace('\n', ''))

        if is_quote_rt:
            # 引用RTは短め（URL分を考慮）
            min_len = 30
            max_len = 250
        else:
            min_len = content_rules.get("min_length", 40)
            max_len = content_rules.get("max_length", 280)

        if text_len < min_len:
            violations.append(f"文字数不足: {text_len}字 (最低{min_len}字)")
        if text_len > max_len:
            violations.append(f"文字数超過: {text_len}字 (最大{max_len}字)")

        # 3. ハッシュタグ数チェック
        max_hashtags = content_rules.get("max_hashtags", 3)
        hashtags = re.findall(r'#\S+', text)
        if len(hashtags) > max_hashtags:
            violations.append(f"ハッシュタグ過多: {len(hashtags)}個 (最大{max_hashtags}個)")

        # 4. リンク数チェック（引用RTはURL不要、APIが付与）
        if is_quote_rt:
            links = re.findall(r'https?://\S+', text)
            if len(links) > 0:
                warnings.append("引用RTコメントにURL不要（APIが自動付与）")
        else:
            max_links = content_rules.get("max_links", 1)
            links = re.findall(r'https?://\S+', text)
            if len(links) > max_links:
                violations.append(f"リンク過多: {len(links)}個 (最大{max_links}個)")

        # 5. 絵文字数チェック
        max_emoji = content_rules.get("max_emoji", 3)
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"  # dingbats
            "\U0001F900-\U0001F9FF"  # supplemental symbols
            "\U0001FA00-\U0001FA6F"  # chess symbols
            "\U0001FA70-\U0001FAFF"  # symbols extended-A
            "\U00002600-\U000026FF"  # misc symbols
            "\U0000FE00-\U0000FE0F"  # variation selectors
            "\U0000200D"             # zero width joiner
            "]",
            flags=re.UNICODE
        )
        emojis = emoji_pattern.findall(text)
        emoji_count = len(emojis)
        if emoji_count > max_emoji:
            warnings.append(f"絵文字{emoji_count}個 (推奨{max_emoji}個以下)")

        # 6. 重複チェック
        if past_posts:
            threshold = self.rules.get("quality_rules", {}).get("duplicate_threshold", 0.8)
            for past in past_posts:
                similarity = SequenceMatcher(None, text, past).ratio()
                if similarity >= threshold:
                    violations.append(
                        f"過去投稿と類似度{similarity:.0%} (閾値{threshold:.0%})"
                    )
                    break

        # 7. 投稿間隔チェック（10投稿対応: 60分間隔）
        if last_post_minutes_ago is not None:
            min_interval = self.rules.get("posting_rules", {}).get(
                "posting_interval_min_minutes", 60
            )
            if last_post_minutes_ago < min_interval:
                violations.append(
                    f"投稿間隔不足: {last_post_minutes_ago}分 (最低{min_interval}分)"
                )

        # 8. 引用RT専用チェック
        if is_quote_rt and quote_rt_context:
            qt_violations, qt_warnings = self._check_quote_rt(text, quote_rt_context)
            violations.extend(qt_violations)
            warnings.extend(qt_warnings)

        is_safe = len(violations) == 0
        return SafetyResult(is_safe=is_safe, violations=violations, warnings=warnings)

    def _check_quote_rt(self, text: str, context: dict) -> tuple[list[str], list[str]]:
        """引用RT専用の安全チェック"""
        violations = []
        warnings = []

        # 同一ソースの1日制限
        max_same_source = 1
        if context.get("today_same_source_count", 0) >= max_same_source:
            violations.append(
                f"同一ソース引用が1日{max_same_source}件を超過 "
                f"(@{context.get('source_username', '?')})"
            )

        # 連続引用RT制限
        max_consecutive = 2
        if context.get("consecutive_quote_count", 0) >= max_consecutive:
            warnings.append(
                f"引用RTが{max_consecutive}件連続。オリジナル投稿を挟むことを推奨"
            )

        # 翻訳だけ投稿の検出（禁止パターン）
        banned = ["翻訳しました", "Translation:", "translated"]
        for pattern in banned:
            if pattern.lower() in text.lower():
                violations.append(f"禁止パターン検出: '{pattern}' — 独自コメントを追加してください")
                break

        return violations, warnings

    def _check_ng_words(self, text: str) -> list[str]:
        """NGワードを検出"""
        text_lower = text.lower()
        found = []
        for word in self._ng_words:
            if word.lower() in text_lower:
                found.append(word)
        return found

    def format_result(self, result: SafetyResult) -> str:
        """結果をフォーマット"""
        lines = []
        if result.is_safe:
            lines.append("🛡️ 安全チェック: ✅ PASS")
        else:
            lines.append("🛡️ 安全チェック: ❌ FAIL")
            for v in result.violations:
                lines.append(f"  ⛔ {v}")
        for w in result.warnings:
            lines.append(f"  ⚠️ {w}")
        return '\n'.join(lines)
