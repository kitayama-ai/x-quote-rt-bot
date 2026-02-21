"""
X Auto Post System — 週次レポート生成

DESIGN.md §8-2 のフォーマットで週次分析レポートを生成。
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.config import Config, PROJECT_ROOT
from src.analyze.metrics_collector import MetricsCollector

JST = ZoneInfo("Asia/Tokyo")


class WeeklyReporter:
    """週次レポート生成"""

    def __init__(self, config: Config):
        self.config = config

    def generate_report(self, metrics: list[dict]) -> str:
        """
        週次分析レポートを生成

        Args:
            metrics: MetricsCollector.collect_recent() の結果
        """
        collector = MetricsCollector(self.config)
        summary = collector.calculate_summary(metrics)

        now = datetime.now(JST)
        week_start = (now - timedelta(days=7)).strftime("%m/%d")
        week_end = now.strftime("%m/%d")

        report = f"""📈 **週次レポート — {self.config.account_name}**
📅 期間: {week_start} 〜 {week_end}

━━━━━━━━━━━━━━━━━━
**📊 KPI サマリー**
━━━━━━━━━━━━━━━━━━
投稿数: {summary.get('post_count', 0)}本
平均いいね: {summary.get('avg_likes', 0)}
平均RT: {summary.get('avg_retweets', 0)}
平均リプライ: {summary.get('avg_replies', 0)}
エンゲージメント率: {summary.get('engagement_rate', 0)}%
総インプレッション: {summary.get('total_impressions', 0):,}

━━━━━━━━━━━━━━━━━━
**🏆 ベスト投稿**
━━━━━━━━━━━━━━━━━━
{summary.get('best_tweet', '—')}
👍 {summary.get('best_likes', 0)}いいね

━━━━━━━━━━━━━━━━━━
**📋 投稿タイプ別パフォーマンス**
━━━━━━━━━━━━━━━━━━
"""
        # タイプ別にグループ化
        type_metrics = {}
        for m in metrics:
            # dailyファイルから投稿タイプを推測（実際はjoinが必要）
            engagement = m.get("likes", 0) + m.get("retweets", 0) * 3
            type_metrics.setdefault("全体", []).append(engagement)

        for ptype, engagements in type_metrics.items():
            avg = sum(engagements) / len(engagements) if engagements else 0
            report += f"- {ptype}: 平均エンゲージメント {avg:.1f}\n"

        report += f"""
━━━━━━━━━━━━━━━━━━
**💡 改善ポイント（自動分析）**
━━━━━━━━━━━━━━━━━━
"""
        # 簡易改善提案
        if summary.get('avg_likes', 0) < 5:
            report += "- ⚠️ 平均いいねが少ない → フックを強化、数字を入れる\n"
        if summary.get('engagement_rate', 0) < 1.0:
            report += "- ⚠️ エンゲージメント率低い → CTA（問いかけ）を強化\n"
        if summary.get('avg_retweets', 0) < 1:
            report += "- ⚠️ RTが少ない → 共感性のある「反常識」系を増やす\n"
        if summary.get('avg_replies', 0) < 1:
            report += "- ⚠️ リプライが少ない → 「〜してる人いる？」系のCTA追加\n"

        if (summary.get('avg_likes', 0) >= 5
                and summary.get('engagement_rate', 0) >= 1.0):
            report += "- ✅ 順調！現在の方針を継続\n"

        # 選定PDCAセクション
        try:
            from src.pdca.preference_updater import PreferenceUpdater
            updater = PreferenceUpdater()
            pdca_report = updater.generate_report()
            report += f"\n{pdca_report}\n"
        except Exception:
            pass  # フィードバックデータがない場合はスキップ

        return report

    def save_report(self, report: str) -> Path:
        """レポートをファイルに保存"""
        output_dir = PROJECT_ROOT / "data" / "output" / "analysis"
        output_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now(JST).date().isoformat()
        filepath = output_dir / f"weekly_report_{today}_{self.config.account_id}.md"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)

        print(f"📁 週次レポート保存: {filepath}")
        return filepath
