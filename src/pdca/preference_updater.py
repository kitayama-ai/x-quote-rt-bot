"""
X Auto Post System — 選定プリファレンス自動調整

フィードバックデータ（承認/スキップ判断）を分析し、
クライアントの好みに合わせてツイート選定プリファレンスを自動調整する。
週次PDCAサイクルの「Act」フェーズ。
"""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.config import PROJECT_ROOT

JST = ZoneInfo("Asia/Tokyo")

FEEDBACK_FILE = PROJECT_ROOT / "data" / "feedback" / "selection_feedback.json"
PREFERENCES_FILE = PROJECT_ROOT / "config" / "selection_preferences.json"

# 調整ルール
MIN_DECISIONS_FOR_ADJUST = 10   # 最低判断数（これ未満は調整しない）
PROMOTE_THRESHOLD = 0.80        # 承認率がこれ以上 → ブースト
DEMOTE_THRESHOLD = 0.30         # 承認率がこれ以下 → ペナルティ
MAX_WEIGHT_CHANGE = 0.5         # 1サイクルの最大調整幅


class PreferenceUpdater:
    """フィードバックデータから選定プリファレンスを自動調整"""

    def __init__(self):
        self._load_data()

    def _load_data(self):
        """フィードバック + プリファレンスを読み込み"""
        try:
            with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
                self._feedback = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._feedback = {"entries": [], "stats": {}}

        try:
            with open(PREFERENCES_FILE, "r", encoding="utf-8") as f:
                self._prefs = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._prefs = {}

    def analyze_feedback(self) -> dict:
        """
        フィードバックデータを分析し、推奨調整を生成

        Returns:
            {
                "total_decisions": int,
                "approval_rate": float,
                "account_recommendations": {
                    "promote": [{"username": str, "rate": float, "count": int}],
                    "demote": [{"username": str, "rate": float, "count": int}],
                },
                "keyword_recommendations": {
                    "boost": [{"keyword": str, "rate": float, "count": int}],
                    "reduce": [{"keyword": str, "rate": float, "count": int}],
                },
                "topic_recommendations": {
                    "boost": [{"topic": str, "rate": float, "count": int}],
                    "reduce": [{"topic": str, "rate": float, "count": int}],
                },
                "top_skip_reasons": [{"reason": str, "count": int}],
            }
        """
        stats = self._feedback.get("stats", {})
        total = stats.get("total", 0)

        if total == 0:
            return {
                "total_decisions": 0,
                "approval_rate": 0.0,
                "account_recommendations": {"promote": [], "demote": []},
                "keyword_recommendations": {"boost": [], "reduce": []},
                "topic_recommendations": {"boost": [], "reduce": []},
                "top_skip_reasons": [],
            }

        approval_rate = stats.get("approval_rate", 0.0)

        # ── ソース別分析 ──
        account_promote = []
        account_demote = []
        for username, src_stats in stats.get("by_source", {}).items():
            approved = src_stats.get("approved", 0)
            skipped = src_stats.get("skipped", 0)
            count = approved + skipped
            if count < MIN_DECISIONS_FOR_ADJUST:
                continue
            rate = approved / count
            entry = {"username": username, "rate": round(rate, 3), "count": count}
            if rate >= PROMOTE_THRESHOLD:
                account_promote.append(entry)
            elif rate <= DEMOTE_THRESHOLD:
                account_demote.append(entry)

        # ── キーワード別分析 ──
        keyword_boost = []
        keyword_reduce = []
        for keyword, kw_stats in stats.get("by_keyword", {}).items():
            approved = kw_stats.get("approved", 0)
            skipped = kw_stats.get("skipped", 0)
            count = approved + skipped
            if count < MIN_DECISIONS_FOR_ADJUST:
                continue
            rate = approved / count
            entry = {"keyword": keyword, "rate": round(rate, 3), "count": count}
            if rate >= PROMOTE_THRESHOLD:
                keyword_boost.append(entry)
            elif rate <= DEMOTE_THRESHOLD:
                keyword_reduce.append(entry)

        # ── トピック別分析 ──
        topic_boost = []
        topic_reduce = []
        for topic, tp_stats in stats.get("by_topic", {}).items():
            approved = tp_stats.get("approved", 0)
            skipped = tp_stats.get("skipped", 0)
            count = approved + skipped
            if count < MIN_DECISIONS_FOR_ADJUST:
                continue
            rate = approved / count
            entry = {"topic": topic, "rate": round(rate, 3), "count": count}
            if rate >= PROMOTE_THRESHOLD:
                topic_boost.append(entry)
            elif rate <= DEMOTE_THRESHOLD:
                topic_reduce.append(entry)

        # ── スキップ理由分析 ──
        skip_reasons = sorted(
            stats.get("by_reason", {}).items(),
            key=lambda x: x[1],
            reverse=True,
        )
        top_skip_reasons = [
            {"reason": r, "count": c} for r, c in skip_reasons[:5]
        ]

        return {
            "total_decisions": total,
            "approval_rate": round(approval_rate, 3),
            "account_recommendations": {
                "promote": sorted(account_promote, key=lambda x: x["rate"], reverse=True),
                "demote": sorted(account_demote, key=lambda x: x["rate"]),
            },
            "keyword_recommendations": {
                "boost": sorted(keyword_boost, key=lambda x: x["rate"], reverse=True),
                "reduce": sorted(keyword_reduce, key=lambda x: x["rate"]),
            },
            "topic_recommendations": {
                "boost": sorted(topic_boost, key=lambda x: x["rate"], reverse=True),
                "reduce": sorted(topic_reduce, key=lambda x: x["rate"]),
            },
            "top_skip_reasons": top_skip_reasons,
        }

    def auto_update(self, dry_run: bool = False) -> dict:
        """
        分析結果に基づいてプリファレンスを自動調整

        Args:
            dry_run: True=変更を保存しない（確認用）

        Returns:
            {"changes": [str], "summary": str}
        """
        analysis = self.analyze_feedback()
        changes = []

        if analysis["total_decisions"] < MIN_DECISIONS_FOR_ADJUST:
            return {
                "changes": [],
                "summary": f"データ不足（{analysis['total_decisions']}/{MIN_DECISIONS_FOR_ADJUST}件）。調整スキップ。",
            }

        # ── キーワード重み調整 ──
        kw_weights = self._prefs.get("keyword_weights", {})

        for entry in analysis["keyword_recommendations"]["boost"]:
            kw = entry["keyword"]
            current = kw_weights.get(kw, 1.0)
            new_val = min(current + 0.2, current + MAX_WEIGHT_CHANGE, 3.0)
            if new_val != current:
                kw_weights[kw] = round(new_val, 1)
                changes.append(f"キーワード '{kw}' weight: {current} → {new_val} (承認率{entry['rate']*100:.0f}%)")

        for entry in analysis["keyword_recommendations"]["reduce"]:
            kw = entry["keyword"]
            current = kw_weights.get(kw, 1.0)
            new_val = max(current - 0.3, current - MAX_WEIGHT_CHANGE, 0.0)
            if new_val != current:
                kw_weights[kw] = round(new_val, 1)
                changes.append(f"キーワード '{kw}' weight: {current} → {new_val} (承認率{entry['rate']*100:.0f}%)")

        self._prefs["keyword_weights"] = kw_weights

        # ── アカウント優先度調整 ──
        ao = self._prefs.setdefault("account_overrides", {})
        boosted = set(ao.get("boosted", []))

        for entry in analysis["account_recommendations"]["promote"]:
            username = entry["username"]
            if username not in boosted:
                boosted.add(username)
                changes.append(f"アカウント @{username} → 優先追加 (承認率{entry['rate']*100:.0f}%)")

        for entry in analysis["account_recommendations"]["demote"]:
            username = entry["username"]
            if username in boosted:
                boosted.discard(username)
                changes.append(f"アカウント @{username} → 優先解除 (承認率{entry['rate']*100:.0f}%)")

        ao["boosted"] = sorted(list(boosted))

        # ── トピック調整 ──
        tp = self._prefs.setdefault("topic_preferences", {})
        preferred = set(tp.get("preferred", []))
        avoid = set(tp.get("avoid", []))

        for entry in analysis["topic_recommendations"]["boost"]:
            topic = entry["topic"]
            if topic in avoid:
                avoid.discard(topic)
                preferred.add(topic)
                changes.append(f"トピック '{topic}' → 回避→優先に変更 (承認率{entry['rate']*100:.0f}%)")
            elif topic not in preferred:
                preferred.add(topic)
                changes.append(f"トピック '{topic}' → 優先追加 (承認率{entry['rate']*100:.0f}%)")

        for entry in analysis["topic_recommendations"]["reduce"]:
            topic = entry["topic"]
            if topic in preferred:
                preferred.discard(topic)
                avoid.add(topic)
                changes.append(f"トピック '{topic}' → 優先→回避に変更 (承認率{entry['rate']*100:.0f}%)")
            elif topic not in avoid:
                avoid.add(topic)
                changes.append(f"トピック '{topic}' → 回避追加 (承認率{entry['rate']*100:.0f}%)")

        tp["preferred"] = sorted(list(preferred))
        tp["avoid"] = sorted(list(avoid))

        # 更新メタデータ
        self._prefs["updated_at"] = datetime.now(JST).isoformat()[:10]
        self._prefs["updated_by"] = "auto_pdca"
        self._prefs["version"] = self._prefs.get("version", 1) + 1

        # 保存
        if not dry_run and changes:
            with open(PREFERENCES_FILE, "w", encoding="utf-8") as f:
                json.dump(self._prefs, f, ensure_ascii=False, indent=2)

        summary = f"調整{len(changes)}件" if changes else "調整なし（条件を満たす項目なし）"
        return {"changes": changes, "summary": summary}

    def generate_report(self) -> str:
        """Discord通知用の選定PDCAレポートを生成"""
        analysis = self.analyze_feedback()

        if analysis["total_decisions"] == 0:
            return "📊 **選定PDCA**: フィードバックデータなし"

        report = f"""🎯 **選定PDCA分析**
━━━━━━━━━━━━━━━━━━
判断数: {analysis['total_decisions']}件
承認率: {analysis['approval_rate']*100:.1f}%
"""

        # トップ承認ソース
        promotes = analysis["account_recommendations"]["promote"]
        if promotes:
            report += "\n✅ **高承認率アカウント:**\n"
            for p in promotes[:3]:
                report += f"  @{p['username']}: {p['rate']*100:.0f}% ({p['count']}件)\n"

        # 低承認率ソース
        demotes = analysis["account_recommendations"]["demote"]
        if demotes:
            report += "\n⚠️ **低承認率アカウント:**\n"
            for d in demotes[:3]:
                report += f"  @{d['username']}: {d['rate']*100:.0f}% ({d['count']}件)\n"

        # スキップ理由
        if analysis["top_skip_reasons"]:
            report += "\n📋 **スキップ理由TOP:**\n"
            reason_labels = {
                "topic_mismatch": "トピック不一致",
                "source_untrusted": "ソース不適切",
                "too_old": "古すぎる",
                "low_quality": "品質不足",
                "off_brand": "ブランド不適合",
                "other": "その他",
            }
            for sr in analysis["top_skip_reasons"][:3]:
                label = reason_labels.get(sr["reason"], sr["reason"])
                report += f"  {label}: {sr['count']}件\n"

        return report
