"""
X Auto Post System — マスターデータ自動更新

週次分析の結果から勝ちパターンを抽出し、マスターデータを自動更新。
"""
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.config import Config, PROJECT_ROOT

JST = ZoneInfo("Asia/Tokyo")


class MasterUpdater:
    """マスターデータの自動更新"""

    def __init__(self, config: Config):
        self.config = config

    def update_from_metrics(self, metrics: list[dict]) -> str:
        """
        メトリクスデータから学習し、マスターデータの更新ログに追記

        Args:
            metrics: MetricsCollector.collect_recent() の結果

        Returns:
            更新内容の説明テキスト
        """
        if not metrics:
            return "メトリクスデータなし。更新スキップ。"

        # ベスト/ワースト分析
        sorted_by_engagement = sorted(
            metrics,
            key=lambda m: m.get("likes", 0) + m.get("retweets", 0) * 3,
            reverse=True
        )

        best_posts = sorted_by_engagement[:3]
        worst_posts = sorted_by_engagement[-3:]

        # パターン分析
        findings = []

        # ベスト投稿の共通パターンを検出
        best_texts = [m.get("text", "") for m in best_posts]
        patterns = self._detect_patterns(best_texts)
        if patterns:
            findings.append(f"勝ちパターン: {', '.join(patterns)}")

        # ワースト投稿のパターンを検出
        worst_texts = [m.get("text", "") for m in worst_posts]
        anti_patterns = self._detect_patterns(worst_texts)
        if anti_patterns:
            findings.append(f"負けパターン: {', '.join(anti_patterns)}")

        # マスターデータに更新ログを追記
        today = datetime.now(JST).strftime("%Y/%m/%d")
        update_entry = f"| {today} | 週次分析: {'; '.join(findings) if findings else '特筆事項なし'} |"

        master_path = self.config.master_data_path
        with open(master_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 更新ログテーブルの最後に追記
        if "## 更新ログ" in content:
            content = content.rstrip() + f"\n{update_entry}\n"
        else:
            content += f"\n\n## 更新ログ\n\n| 日付 | 更新内容 |\n|---|---|\n{update_entry}\n"

        with open(master_path, "w", encoding="utf-8") as f:
            f.write(content)

        summary = f"マスターデータ更新完了: {'; '.join(findings)}" if findings else "更新内容なし"
        print(f"📝 {summary}")
        return summary

    def _detect_patterns(self, texts: list[str]) -> list[str]:
        """テキスト群から共通パターンを検出"""
        patterns = []

        # 書き出しパターン
        starts = []
        for text in texts:
            first_line = text.split('\n')[0] if text else ""
            if re.match(r'^(ぶっちゃけ|正直|マジで)', first_line):
                starts.append("自己開示系フック")
            elif re.match(r'^\d+', first_line):
                starts.append("数字フック")
            elif re.match(r'^(やばい|えぐい|これ)', first_line):
                starts.append("感情フック")

        if starts:
            most_common = max(set(starts), key=starts.count)
            patterns.append(f"フック:{most_common}")

        # 具体性の有無
        has_numbers = sum(1 for t in texts if re.search(r'\d+[万円%時間分]', t))
        if has_numbers >= 2:
            patterns.append("具体的数字あり")

        # 長さ分析
        avg_len = sum(len(t.replace('\n', '')) for t in texts) / max(len(texts), 1)
        if avg_len < 140:
            patterns.append("短文(〜140字)")
        elif avg_len > 220:
            patterns.append("長文(220字+)")

        return patterns
