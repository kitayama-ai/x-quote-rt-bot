"""
X Auto Post System — 投稿ミックスプランナー

引用RT / オリジナル投稿の比率管理、時間分散、連続投稿制限を管理。
BAN対策の核となるモジュール。
"""
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.config import PROJECT_ROOT

JST = ZoneInfo("Asia/Tokyo")


# 10スロットの基本スケジュール
# type_pool: このスロットで許可される投稿タイプ
DEFAULT_SLOTS = [
    {"slot_id": "slot_01", "base_hour": 7,  "base_minute": 0,  "jitter_min": 20, "type_pool": ["original"]},
    {"slot_id": "slot_02", "base_hour": 8,  "base_minute": 30, "jitter_min": 25, "type_pool": ["quote_rt"]},
    {"slot_id": "slot_03", "base_hour": 10, "base_minute": 15, "jitter_min": 20, "type_pool": ["quote_rt"]},
    {"slot_id": "slot_04", "base_hour": 12, "base_minute": 0,  "jitter_min": 20, "type_pool": ["original"]},
    {"slot_id": "slot_05", "base_hour": 14, "base_minute": 15, "jitter_min": 20, "type_pool": ["quote_rt"]},
    {"slot_id": "slot_06", "base_hour": 16, "base_minute": 0,  "jitter_min": 25, "type_pool": ["quote_rt"]},
    {"slot_id": "slot_07", "base_hour": 18, "base_minute": 0,  "jitter_min": 20, "type_pool": ["quote_rt"]},
    {"slot_id": "slot_08", "base_hour": 19, "base_minute": 45, "jitter_min": 15, "type_pool": ["original"]},
    {"slot_id": "slot_09", "base_hour": 21, "base_minute": 0,  "jitter_min": 20, "type_pool": ["quote_rt"]},
    {"slot_id": "slot_10", "base_hour": 22, "base_minute": 30, "jitter_min": 25, "type_pool": ["quote_rt", "original"]},
]

# 最小投稿間隔（分）
MIN_INTERVAL_MINUTES = 60


class MixPlanner:
    """引用RT/オリジナルの投稿ミックスを計画"""

    def __init__(self):
        # 引用RTルール読み込み
        rules_path = PROJECT_ROOT / "config" / "quote_rt_rules.json"
        if rules_path.exists():
            with open(rules_path, "r", encoding="utf-8") as f:
                self.rules = json.load(f)
        else:
            self.rules = {}

        self.mix_rules = self.rules.get("mix_rules", {})

    def get_warmup_limits(self, account_start_date: str = "") -> dict:
        """
        ウォームアップスケジュールに基づく本日の投稿制限を取得

        Args:
            account_start_date: アカウント運用開始日（YYYY-MM-DD）。空なら制限なし。

        Returns:
            {"daily_quotes": int, "daily_originals": int, "phase": str}
        """
        if not account_start_date:
            return {"daily_quotes": 99, "daily_originals": 99, "phase": "フル稼働"}

        warmup = self.rules.get("warmup_schedule", {})
        if not warmup:
            return {"daily_quotes": 99, "daily_originals": 99, "phase": "フル稼働"}

        try:
            start = datetime.strptime(account_start_date, "%Y-%m-%d").date()
            elapsed_days = (datetime.now(JST).date() - start).days
        except (ValueError, TypeError):
            return {"daily_quotes": 99, "daily_originals": 99, "phase": "フル稼働"}

        if elapsed_days < 4:
            phase = warmup.get("week_0", {})
            return {"daily_quotes": phase.get("daily_quotes", 0), "daily_originals": phase.get("daily_originals", 3), "phase": "week_0"}
        elif elapsed_days < 8:
            phase = warmup.get("week_1", {})
            return {"daily_quotes": phase.get("daily_quotes", 1), "daily_originals": phase.get("daily_originals", 3), "phase": "week_1"}
        elif elapsed_days < 15:
            phase = warmup.get("week_2", {})
            return {"daily_quotes": phase.get("daily_quotes", 2), "daily_originals": phase.get("daily_originals", 5), "phase": "week_2"}
        elif elapsed_days < 22:
            phase = warmup.get("week_3", {})
            return {"daily_quotes": phase.get("daily_quotes", 4), "daily_originals": phase.get("daily_originals", 4), "phase": "week_3"}
        else:
            phase = warmup.get("week_4_plus", {})
            return {"daily_quotes": phase.get("daily_quotes", 7), "daily_originals": phase.get("daily_originals", 3), "phase": "week_4+"}

    def plan_daily(self, available_quotes: int = 10, account_start_date: str = "") -> list[dict]:
        """
        1日分の投稿スケジュールを計画

        Args:
            available_quotes: 利用可能な引用RTの候補数
            account_start_date: アカウント運用開始日（ウォームアップ制御用）

        Returns:
            [{"slot_id", "time", "type", "base_hour", ...}]
        """
        # ウォームアップ制限を取得
        warmup = self.get_warmup_limits(account_start_date)
        max_quotes_warmup = warmup["daily_quotes"]
        max_originals_warmup = warmup["daily_originals"]

        if warmup["phase"] != "フル稼働":
            print(f"  🌱 ウォームアップ中 [{warmup['phase']}]: 引用RT最大{max_quotes_warmup}件 / オリジナル最大{max_originals_warmup}件")

        # 今日の投稿数をランダムに決定
        daily_min = self.mix_rules.get("daily_total_min", 7)
        daily_max = self.mix_rules.get("daily_total_max", 10)

        # ウォームアップ制限で上限を調整
        effective_max = min(daily_max, max_quotes_warmup + max_originals_warmup)
        effective_min = min(daily_min, effective_max)
        daily_count = self._random_daily_count(effective_min, effective_max)

        # 使用するスロットを選択
        slots = self._select_slots(daily_count)

        # 各スロットの投稿タイプを決定（ウォームアップ制限を反映）
        effective_quotes = min(available_quotes, max_quotes_warmup)
        plan = self._assign_types(slots, effective_quotes)

        # 投稿時間をランダム化
        plan = self._randomize_times(plan)

        # 投稿間隔チェック
        plan = self._enforce_min_interval(plan)

        return plan

    def _random_daily_count(self, min_count: int, max_count: int) -> int:
        """日次投稿数をランダムに決定（多い方に偏る重み付け）"""
        weights = []
        for i in range(min_count, max_count + 1):
            # 多い方が高確率（例: 7=5%, 8=15%, 9=30%, 10=50%）
            weights.append((i - min_count + 1) ** 2)
        return random.choices(range(min_count, max_count + 1), weights=weights)[0]

    def _select_slots(self, count: int) -> list[dict]:
        """使用するスロットを選択（count件）"""
        if count >= len(DEFAULT_SLOTS):
            return list(DEFAULT_SLOTS)

        # 最初と最後は必ず含める + 残りをランダム選択
        selected = [DEFAULT_SLOTS[0], DEFAULT_SLOTS[-1]]
        remaining = DEFAULT_SLOTS[1:-1]
        random.shuffle(remaining)
        selected.extend(remaining[:count - 2])

        # 時間順にソート
        selected.sort(key=lambda s: (s["base_hour"], s["base_minute"]))
        return selected

    def _assign_types(self, slots: list[dict], available_quotes: int) -> list[dict]:
        """各スロットに投稿タイプを割り当て"""
        plan = []
        quote_count = 0
        original_count = 0

        # 目標比率
        quote_ratio_max = self.mix_rules.get("quote_rt_ratio_max", 0.7)
        max_quotes = int(len(slots) * quote_ratio_max)
        max_quotes = min(max_quotes, available_quotes)

        for slot in slots:
            pool = slot["type_pool"]

            # 連続引用RT制限チェック
            max_consecutive = self.rules.get("quote_rt", {}).get("max_consecutive_quotes", 2)
            recent_types = [p["type"] for p in plan[-max_consecutive:]]
            consecutive_quotes = all(t == "quote_rt" for t in recent_types) if recent_types else False

            if consecutive_quotes and len(recent_types) >= max_consecutive:
                # 連続制限に達した → オリジナルを強制
                post_type = "original"
            elif "quote_rt" in pool and quote_count < max_quotes:
                post_type = "quote_rt"
            else:
                # 引用RT枠を使い切った or poolにquote_rtがない → オリジナル
                post_type = "original"

            if post_type == "quote_rt":
                quote_count += 1
            else:
                original_count += 1

            plan.append({
                **slot,
                "type": post_type,
            })

        return plan

    def _randomize_times(self, plan: list[dict]) -> list[dict]:
        """投稿時間にランダムジッターを追加"""
        for item in plan:
            jitter = random.randint(-item["jitter_min"], item["jitter_min"])
            hour = item["base_hour"]
            minute = item["base_minute"] + jitter

            if minute < 0:
                hour -= 1
                minute += 60
            elif minute >= 60:
                hour += 1
                minute -= 60

            # 時間の範囲チェック
            hour = max(6, min(23, hour))
            minute = max(0, min(59, minute))

            item["time"] = f"{hour:02d}:{minute:02d}"
            item["scheduled_hour"] = hour
            item["scheduled_minute"] = minute

        return plan

    def _enforce_min_interval(self, plan: list[dict]) -> list[dict]:
        """最小投稿間隔を確保"""
        for i in range(1, len(plan)):
            prev_time = plan[i - 1]["scheduled_hour"] * 60 + plan[i - 1]["scheduled_minute"]
            curr_time = plan[i]["scheduled_hour"] * 60 + plan[i]["scheduled_minute"]
            diff = curr_time - prev_time

            if diff < MIN_INTERVAL_MINUTES:
                # 現在のスロットを後ろにずらす
                new_minute = prev_time + MIN_INTERVAL_MINUTES
                plan[i]["scheduled_hour"] = new_minute // 60
                plan[i]["scheduled_minute"] = new_minute % 60
                plan[i]["time"] = f"{plan[i]['scheduled_hour']:02d}:{plan[i]['scheduled_minute']:02d}"

        return plan

    def get_slot_for_now(self, plan: list[dict], tolerance_minutes: int = 30) -> dict | None:
        """現在時刻に該当するスロットを返す"""
        now = datetime.now(JST)
        now_minutes = now.hour * 60 + now.minute

        for slot in plan:
            slot_minutes = slot["scheduled_hour"] * 60 + slot["scheduled_minute"]
            if abs(now_minutes - slot_minutes) <= tolerance_minutes:
                return slot

        return None

    def format_plan(self, plan: list[dict]) -> str:
        """プランを表示用にフォーマット"""
        lines = ["📋 本日の投稿スケジュール:", ""]
        for i, item in enumerate(plan, 1):
            icon = "🔄" if item["type"] == "quote_rt" else "✍️"
            lines.append(
                f"  {i}. {item['time']}  {icon} {item['type']:10s}  ({item['slot_id']})"
            )

        # 集計
        qt = sum(1 for p in plan if p["type"] == "quote_rt")
        og = sum(1 for p in plan if p["type"] == "original")
        lines.append("")
        lines.append(f"  合計: {len(plan)}件 (引用RT: {qt} / オリジナル: {og})")

        return "\n".join(lines)
