"""
X Auto Post System — メトリクス収集

X APi v2でエンゲージメントを取得し、Google Sheetsに保存。
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.config import Config, PROJECT_ROOT
from src.post.x_poster import XPoster

JST = ZoneInfo("Asia/Tokyo")


class MetricsCollector:
    """X APIからメトリクスを収集"""

    def __init__(self, config: Config):
        self.config = config
        self.poster = XPoster(config)

    def collect_recent(self, days: int = 7) -> list[dict]:
        """
        直近N日間の投稿のメトリクスを収集

        Returns:
            [{"tweet_id", "text", "created_at", "likes", "retweets", ...}]
        """
        # 最近のツイートを取得
        tweets = self.poster.get_recent_tweets(max_results=min(days * 3, 50))

        results = []
        for tweet in tweets:
            try:
                metrics = self.poster.get_tweet_metrics(tweet["id"])
                results.append({
                    "tweet_id": tweet["id"],
                    "text": tweet["text"][:100],  # 先頭100文字
                    "created_at": str(tweet.get("created_at", "")),
                    **metrics,
                    "collected_at": datetime.now(JST).isoformat()
                })
            except Exception as e:
                print(f"⚠️ メトリクス取得エラー ({tweet['id']}): {e}")

        return results

    def save_metrics(self, metrics: list[dict]) -> Path:
        """メトリクスをJSONファイルに保存"""
        output_dir = PROJECT_ROOT / "data" / "output" / "analysis"
        output_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now(JST).date().isoformat()
        filepath = output_dir / f"metrics_{today}_{self.config.account_id}.json"

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)

        print(f"📁 メトリクス保存: {filepath}")
        return filepath

    def calculate_summary(self, metrics: list[dict]) -> dict:
        """メトリクスのサマリーを計算"""
        if not metrics:
            return {}

        total_likes = sum(m.get("likes", 0) for m in metrics)
        total_retweets = sum(m.get("retweets", 0) for m in metrics)
        total_replies = sum(m.get("replies", 0) for m in metrics)
        total_impressions = sum(m.get("impressions", 0) for m in metrics)
        count = len(metrics)

        engagement_rate = 0
        if total_impressions > 0:
            engagement_rate = (total_likes + total_retweets + total_replies) / total_impressions * 100

        # ベスト投稿
        best = max(metrics, key=lambda m: m.get("likes", 0) + m.get("retweets", 0) * 3)

        return {
            "post_count": count,
            "total_likes": total_likes,
            "total_retweets": total_retweets,
            "total_replies": total_replies,
            "total_impressions": total_impressions,
            "avg_likes": round(total_likes / count, 1),
            "avg_retweets": round(total_retweets / count, 1),
            "avg_replies": round(total_replies / count, 1),
            "engagement_rate": round(engagement_rate, 2),
            "best_tweet": best.get("text", "")[:80],
            "best_likes": best.get("likes", 0)
        }
