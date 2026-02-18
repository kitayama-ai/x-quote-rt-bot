"""
X Auto Post System — 投稿スケジューラー

投稿時間管理（7:00, 12:00, 21:00 ±15分ランダム化）。
GitHub Actions の cron から呼ばれた際に、今が投稿時間かを判定。
"""
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.config import Config, PROJECT_ROOT


JST = ZoneInfo("Asia/Tokyo")


class Scheduler:
    """投稿スケジュール管理"""

    def __init__(self, config: Config):
        self.config = config

    def get_next_post_time(self, slot_name: str) -> datetime:
        """
        指定スロットの次の投稿時間を計算（±ランダム）

        Args:
            slot_name: "morning", "noon", "evening"
        """
        now = datetime.now(JST)
        slot = self.config.schedule[slot_name]

        jitter = random.randint(
            -slot["jitter_minutes"],
            slot["jitter_minutes"]
        )

        post_time = now.replace(
            hour=slot["base_hour"],
            minute=slot["base_minute"],
            second=0,
            microsecond=0
        ) + timedelta(minutes=jitter)

        # 過去の時間なら翌日にする
        if post_time < now:
            post_time += timedelta(days=1)

        return post_time

    def is_posting_time(self, tolerance_minutes: int = 30) -> str | None:
        """
        今が投稿時間帯かどうかを判定

        Returns:
            スロット名 ("morning", "noon", "evening") or None
        """
        now = datetime.now(JST)

        for slot_name in ["morning", "noon", "evening"]:
            slot = self.config.schedule[slot_name]
            target = now.replace(
                hour=slot["base_hour"],
                minute=slot["base_minute"],
                second=0,
                microsecond=0
            )

            diff = abs((now - target).total_seconds()) / 60

            if diff <= tolerance_minutes:
                return slot_name

        return None

    def get_pending_posts(self) -> list[dict]:
        """
        保存されたdailyファイルの中で、まだ投稿されていないものを取得
        """
        today = datetime.now(JST).date().isoformat()
        daily_dir = PROJECT_ROOT / "data" / "output" / "daily"

        if not daily_dir.exists():
            return []

        # 今日のファイルを探す
        files = list(daily_dir.glob(f"{today}_*.json"))
        if not files:
            return []

        pending = []
        for filepath in files:
            with open(filepath, "r", encoding="utf-8") as f:
                posts = json.load(f)
            for post in posts:
                if not post.get("posted", False):
                    pending.append({**post, "_filepath": str(filepath)})

        return pending

    def mark_as_posted(self, filepath: str, slot: str, tweet_id: str):
        """投稿済みマークを付ける"""
        with open(filepath, "r", encoding="utf-8") as f:
            posts = json.load(f)

        for post in posts:
            if post.get("slot") == slot:
                post["posted"] = True
                post["tweet_id"] = tweet_id
                post["posted_at"] = datetime.now(JST).isoformat()
                break

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(posts, f, ensure_ascii=False, indent=2)

    def should_post_now(self, post: dict, tolerance_minutes: int = 30) -> bool:
        """この投稿を今投稿すべきかどうか"""
        now = datetime.now(JST)
        slot = self.config.schedule.get(post.get("slot", ""))
        if not slot:
            return False

        target = now.replace(
            hour=slot["base_hour"],
            minute=slot["base_minute"],
            second=0,
            microsecond=0
        )
        diff = abs((now - target).total_seconds()) / 60
        return diff <= tolerance_minutes
