"""
テスト — MixPlanner ウォームアップスケジュール & get_slot_for_now
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from src.post.mix_planner import MixPlanner

JST = ZoneInfo("Asia/Tokyo")


class TestWarmupLimits:
    """ウォームアップスケジュールのテスト"""

    def setup_method(self):
        self.planner = MixPlanner()

    def test_no_start_date(self):
        """開始日なし → 制限なし"""
        limits = self.planner.get_warmup_limits("")
        assert limits["daily_quotes"] == 99
        assert limits["phase"] == "フル稼働"

    def test_week_0(self):
        """開始1-3日目: 引用RTなし"""
        today = datetime.now(JST).date()
        start = (today - timedelta(days=1)).isoformat()
        limits = self.planner.get_warmup_limits(start)
        assert limits["phase"] == "week_0"
        assert limits["daily_quotes"] == 0

    def test_week_1(self):
        """開始4-7日目: 引用RT1件/日"""
        today = datetime.now(JST).date()
        start = (today - timedelta(days=5)).isoformat()
        limits = self.planner.get_warmup_limits(start)
        assert limits["phase"] == "week_1"
        assert limits["daily_quotes"] >= 1

    def test_week_2(self):
        """開始8-14日目: 引用RT2件/日"""
        today = datetime.now(JST).date()
        start = (today - timedelta(days=10)).isoformat()
        limits = self.planner.get_warmup_limits(start)
        assert limits["phase"] == "week_2"
        assert limits["daily_quotes"] >= 2

    def test_week_3(self):
        """開始15-21日目"""
        today = datetime.now(JST).date()
        start = (today - timedelta(days=18)).isoformat()
        limits = self.planner.get_warmup_limits(start)
        assert limits["phase"] == "week_3"
        assert limits["daily_quotes"] >= 3

    def test_week_4_plus(self):
        """開始22日以降: フル稼働"""
        today = datetime.now(JST).date()
        start = (today - timedelta(days=30)).isoformat()
        limits = self.planner.get_warmup_limits(start)
        assert limits["phase"] == "week_4+"
        assert limits["daily_quotes"] >= 5

    def test_invalid_date(self):
        """無効な日付形式 → 制限なし"""
        limits = self.planner.get_warmup_limits("invalid-date")
        assert limits["daily_quotes"] == 99
        assert limits["phase"] == "フル稼働"

    def test_warmup_limits_daily_plan(self):
        """ウォームアップ中はplan_dailyの投稿数が制限される"""
        today = datetime.now(JST).date()
        start = (today - timedelta(days=1)).isoformat()  # week_0

        plan = self.planner.plan_daily(
            available_quotes=10,
            account_start_date=start,
        )
        quote_count = sum(1 for p in plan if p["type"] == "quote_rt")
        # week_0: 引用RTは0件
        assert quote_count == 0


class TestGetSlotForNow:
    """get_slot_for_now のテスト"""

    def setup_method(self):
        self.planner = MixPlanner()

    def test_matching_slot(self):
        """現在時刻に近いスロットが返る"""
        now = datetime.now(JST)
        plan = [
            {
                "slot_id": "test",
                "type": "quote_rt",
                "time": f"{now.hour:02d}:{now.minute:02d}",
                "scheduled_hour": now.hour,
                "scheduled_minute": now.minute,
            }
        ]
        result = self.planner.get_slot_for_now(plan, tolerance_minutes=5)
        assert result is not None
        assert result["slot_id"] == "test"

    def test_no_matching_slot(self):
        """該当スロットなし"""
        plan = [
            {
                "slot_id": "far_away",
                "type": "original",
                "time": "03:00",
                "scheduled_hour": 3,
                "scheduled_minute": 0,
            }
        ]
        now = datetime.now(JST)
        if now.hour != 3:
            result = self.planner.get_slot_for_now(plan, tolerance_minutes=5)
            assert result is None


class TestSelectSlots:
    """_select_slots のテスト"""

    def setup_method(self):
        self.planner = MixPlanner()

    def test_select_all_slots(self):
        """全スロット使用時"""
        slots = self.planner._select_slots(10)
        assert len(slots) == 10

    def test_select_fewer_slots(self):
        """一部スロットのみ使用"""
        slots = self.planner._select_slots(7)
        assert len(slots) == 7

    def test_slots_sorted_by_time(self):
        """スロットが時間順"""
        for _ in range(10):
            slots = self.planner._select_slots(8)
            for i in range(1, len(slots)):
                prev = slots[i-1]["base_hour"] * 60 + slots[i-1]["base_minute"]
                curr = slots[i]["base_hour"] * 60 + slots[i]["base_minute"]
                assert curr >= prev
