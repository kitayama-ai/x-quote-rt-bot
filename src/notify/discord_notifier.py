"""
X Auto Post System — Discord Webhook通知

投稿案の承認依頼、メトリクス、安全アラートをDiscordに通知。
DESIGN.md §7-2 のフォーマットを実装。
"""
import json
import requests
from datetime import datetime


class DiscordNotifier:
    """Discord Webhook通知"""

    # Embed カラー
    COLOR_SUCCESS = 0x00D26A   # 緑
    COLOR_WARNING = 0xFFAA00   # 黄色
    COLOR_DANGER = 0xFF4444    # 赤
    COLOR_INFO = 0x4DB8FF      # ブルー
    COLOR_PURPLE = 0x9B59B6    # 紫

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, content: str = "", embeds: list[dict] | None = None) -> bool:
        """メッセージを送信"""
        if not self.webhook_url:
            print("[Discord] Webhook URL未設定。通知をスキップ。")
            return False

        payload = {}
        if content:
            payload["content"] = content
        if embeds:
            payload["embeds"] = embeds

        try:
            resp = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            print(f"[Discord] 通知エラー: {e}")
            return False

    def notify_daily_posts(
        self,
        account_name: str,
        account_handle: str,
        posts: list[dict],
        date: str | None = None
    ) -> bool:
        """
        日次投稿案を通知

        posts: [{"text": str, "type": str, "time": str, "score": ScoreResult, "safety": SafetyResult}]
        """
        date = date or datetime.now().strftime("%Y/%m/%d")

        embeds = []

        # ヘッダーEmbed
        embeds.append({
            "title": f"🤖 {account_name} — 本日の投稿案 ({date})",
            "description": f"**{account_handle}** の投稿案 {len(posts)}本",
            "color": self.COLOR_INFO
        })

        # 各投稿のEmbed
        for i, post in enumerate(posts, 1):
            score = post.get("score")
            safety = post.get("safety")
            time_str = post.get("time", "")
            post_type = post.get("type", "")

            # スコア表示
            score_text = ""
            if score:
                rank_emoji = {"S": "🏆", "A": "🥇", "B": "🥈", "C": "🥉"}.get(score.rank, "")
                score_text = (
                    f"\n\n📊 **スコア: {score.total}/8** {rank_emoji} [{score.rank}]\n"
                    f"├ フック力: {score.hook}/2\n"
                    f"├ 具体性: {score.specificity}/2\n"
                    f"├ 人間味: {score.humanity}/2\n"
                    f"├ 構成: {score.structure}/1\n"
                    f"└ CTA: {score.cta}/1"
                )

            # 安全チェック表示
            safety_text = ""
            if safety:
                if safety.is_safe:
                    safety_text = "\n🛡️ 安全チェック: ✅ PASS"
                else:
                    safety_text = f"\n🛡️ 安全チェック: ❌ FAIL\n" + \
                        '\n'.join(f"  ⛔ {v}" for v in safety.violations)

            # 色をスコアで変える
            if score and score.total >= 8:
                color = self.COLOR_SUCCESS
            elif score and score.total >= 6:
                color = self.COLOR_INFO
            elif score and score.total >= 4:
                color = self.COLOR_WARNING
            else:
                color = self.COLOR_DANGER

            embeds.append({
                "title": f"📝 投稿 {i}/{len(posts)} ({time_str} 予定) [{post_type}]",
                "description": f"```\n{post['text']}\n```{score_text}{safety_text}",
                "color": color
            })

        # フッター
        embeds.append({
            "description": "✅ 承認  |  ✏️ 修正依頼  |  ❌ スキップ",
            "color": self.COLOR_PURPLE
        })

        return self.send(embeds=embeds)

    def notify_post_completed(
        self,
        account_name: str,
        tweet_text: str,
        tweet_id: str
    ) -> bool:
        """投稿完了通知"""
        embed = {
            "title": f"✅ 投稿完了 — {account_name}",
            "description": f"```\n{tweet_text[:200]}\n```",
            "fields": [
                {"name": "Tweet ID", "value": tweet_id, "inline": True},
                {
                    "name": "URL",
                    "value": f"https://x.com/i/status/{tweet_id}",
                    "inline": True
                }
            ],
            "color": self.COLOR_SUCCESS,
            "timestamp": datetime.utcnow().isoformat()
        }
        return self.send(embeds=[embed])

    def notify_safety_alert(
        self,
        account_name: str,
        tweet_text: str,
        violations: list[str]
    ) -> bool:
        """安全チェック不合格通知"""
        embed = {
            "title": f"🚨 安全チェック不合格 — {account_name}",
            "description": f"```\n{tweet_text[:200]}\n```",
            "fields": [
                {
                    "name": "違反内容",
                    "value": '\n'.join(f"⛔ {v}" for v in violations)
                }
            ],
            "color": self.COLOR_DANGER,
            "timestamp": datetime.utcnow().isoformat()
        }
        return self.send(embeds=[embed])

    def notify_metrics(
        self,
        account_name: str,
        metrics: dict
    ) -> bool:
        """日次メトリクス通知"""
        embed = {
            "title": f"📊 日次メトリクス — {account_name}",
            "fields": [
                {
                    "name": "フォロワー",
                    "value": str(metrics.get("followers", "—")),
                    "inline": True
                },
                {
                    "name": "平均いいね",
                    "value": str(metrics.get("avg_likes", "—")),
                    "inline": True
                },
                {
                    "name": "平均RT",
                    "value": str(metrics.get("avg_retweets", "—")),
                    "inline": True
                },
                {
                    "name": "エンゲージメント率",
                    "value": f"{metrics.get('engagement_rate', 0):.1f}%",
                    "inline": True
                }
            ],
            "color": self.COLOR_INFO,
            "timestamp": datetime.utcnow().isoformat()
        }
        return self.send(embeds=[embed])

    def notify_error(self, title: str, error_message: str) -> bool:
        """エラー通知"""
        embed = {
            "title": f"⚠️ エラー: {title}",
            "description": f"```\n{error_message[:1000]}\n```",
            "color": self.COLOR_DANGER,
            "timestamp": datetime.utcnow().isoformat()
        }
        return self.send(embeds=[embed])

    def notify_weekly_report(
        self,
        account_name: str,
        report_text: str
    ) -> bool:
        """週次レポート通知"""
        embed = {
            "title": f"📈 週次レポート — {account_name}",
            "description": report_text[:4000],
            "color": self.COLOR_PURPLE,
            "timestamp": datetime.utcnow().isoformat()
        }
        return self.send(embeds=[embed])

    def notify_curate_results(
        self,
        account_name: str,
        results: list[dict],
        plan: list[dict] | None = None,
    ) -> bool:
        """
        引用RT生成結果を通知

        results: [{"text", "template_id", "score", "original_text", "author_username", ...}]
        plan: MixPlannerの日次プラン
        """
        embeds = []

        # ヘッダー
        embeds.append({
            "title": f"🔄 引用RT生成結果 — {account_name}",
            "description": f"**{len(results)}件** の引用RTコメントを生成しました",
            "color": self.COLOR_INFO
        })

        # 各引用RT（最大10件）
        for i, result in enumerate(results[:10], 1):
            score = result.get("score")
            author = result.get("author_username", "?")
            template = result.get("template_id", "?")
            original = result.get("original_text", "")[:100]

            score_text = ""
            if score:
                score_text = f"\n📊 スコア: {score.total}/8 [{score.rank}]"

            color = self.COLOR_SUCCESS if (score and score.total >= 6) else self.COLOR_INFO

            embeds.append({
                "title": f"🔄 引用RT {i}/{len(results)} — @{author} [{template}]",
                "description": (
                    f"**元ツイート:**\n> {original}...\n\n"
                    f"**生成コメント:**\n```\n{result['text'][:300]}\n```"
                    f"{score_text}"
                ),
                "color": color
            })

        # 投稿スケジュール
        if plan:
            schedule_lines = []
            for item in plan:
                icon = "🔄" if item.get("type") == "quote_rt" else "✍️"
                schedule_lines.append(f"{item['time']} {icon} {item.get('type', '?')}")
            schedule_text = '\n'.join(schedule_lines)

            qt = sum(1 for p in plan if p.get("type") == "quote_rt")
            og = sum(1 for p in plan if p.get("type") == "original")

            embeds.append({
                "title": "📋 本日の投稿スケジュール",
                "description": f"```\n{schedule_text}\n```\n合計: {len(plan)}件 (引用RT: {qt} / オリジナル: {og})",
                "color": self.COLOR_PURPLE
            })

        # フッター
        embeds.append({
            "description": "✅ 承認して投稿  |  ✏️ 修正依頼  |  ❌ スキップ\n\n`python -m src.main curate-post` で投稿実行",
            "color": self.COLOR_PURPLE
        })

        return self.send(embeds=embeds)
