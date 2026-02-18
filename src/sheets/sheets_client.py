"""
X Auto Post System — Google Sheets クライアント

スプレッドシートからURL収集シートの読み書きを行う。
パターンA（手動収集）とパターンB（自動収集キュー管理）の両方で使用。
"""
import base64
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials

from src.config import Config

JST = ZoneInfo("Asia/Tokyo")

# スコープ
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

# シート名（パターンA）
SHEET_COLLECT = "URL収集"
SHEET_POSTED = "投稿履歴"
SHEET_METRICS = "メトリクス"

# シート名（パターンB）
SHEET_QUEUE = "キュー管理"
SHEET_COLLECTION_LOG = "収集ログ"
SHEET_DASHBOARD = "ダッシュボード"
SHEET_SETTINGS = "設定"


class SheetsClient:
    """Google Sheets 読み書きクライアント"""

    def __init__(self, config: Config | None = None):
        """
        Args:
            config: Configオブジェクト。Noneなら環境変数から直接取得。
        """
        if config:
            self._spreadsheet_id = config.spreadsheet_id
            creds_b64 = config.google_credentials_base64
        else:
            self._spreadsheet_id = os.getenv("SPREADSHEET_ID", "")
            creds_b64 = os.getenv("GOOGLE_CREDENTIALS_BASE64", "")

        if not self._spreadsheet_id:
            raise ValueError("SPREADSHEET_ID が未設定です")
        if not creds_b64:
            raise ValueError("GOOGLE_CREDENTIALS_BASE64 が未設定です")

        # サービスアカウント認証
        creds_json = json.loads(base64.b64decode(creds_b64))
        credentials = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
        self._gc = gspread.authorize(credentials)
        self._spreadsheet = self._gc.open_by_key(self._spreadsheet_id)

    # === URL収集シート ===

    def get_pending_urls(self) -> list[dict]:
        """
        URL収集シートから未処理のURLを取得

        シート構成:
          A列: URL
          B列: メモ（任意）
          C列: ステータス（空=未処理 / 済 / エラー）
          D列: 追加日時

        Returns:
            [{"row": int, "url": str, "memo": str}]
        """
        try:
            ws = self._spreadsheet.worksheet(SHEET_COLLECT)
        except gspread.exceptions.WorksheetNotFound:
            print(f"[Sheets] '{SHEET_COLLECT}' シートが見つかりません。作成します。")
            ws = self._create_collect_sheet()
            return []

        all_rows = ws.get_all_values()
        pending = []

        for i, row in enumerate(all_rows):
            if i == 0:  # ヘッダー行スキップ
                continue
            if len(row) < 1 or not row[0].strip():
                continue

            url = row[0].strip()
            memo = row[1].strip() if len(row) > 1 else ""
            status = row[2].strip() if len(row) > 2 else ""

            if status == "":  # 未処理のみ
                pending.append({
                    "row": i + 1,  # 1-indexed（GAS/gspread互換）
                    "url": url,
                    "memo": memo,
                })

        return pending

    def mark_url_processed(self, row: int, status: str = "済", tweet_id: str = ""):
        """
        URL収集シートのステータスを更新

        Args:
            row: 行番号（1-indexed）
            status: "済" / "エラー" / "重複"
            tweet_id: キューに追加されたツイートID
        """
        ws = self._spreadsheet.worksheet(SHEET_COLLECT)
        now = datetime.now(JST).strftime("%Y/%m/%d %H:%M")

        # C列: ステータス, D列: 処理日時, E列: ツイートID
        ws.update(f"C{row}:E{row}", [[status, now, tweet_id]])

    def mark_urls_batch(self, updates: list[dict]):
        """
        複数行のステータスを一括更新（API呼び出し回数削減）

        Args:
            updates: [{"row": int, "status": str, "tweet_id": str}]
        """
        if not updates:
            return

        ws = self._spreadsheet.worksheet(SHEET_COLLECT)
        now = datetime.now(JST).strftime("%Y/%m/%d %H:%M")

        batch = []
        for u in updates:
            batch.append({
                "range": f"C{u['row']}:E{u['row']}",
                "values": [[u["status"], now, u.get("tweet_id", "")]],
            })

        ws.batch_update(batch)

    # === 投稿履歴シート ===

    def append_posted(self, record: dict):
        """
        投稿履歴シートにレコード追加

        Args:
            record: {
                "posted_at": str,
                "type": str,
                "text": str,
                "tweet_id": str,
                "score": int,
                "source_url": str,
            }
        """
        try:
            ws = self._spreadsheet.worksheet(SHEET_POSTED)
        except gspread.exceptions.WorksheetNotFound:
            ws = self._create_posted_sheet()

        ws.append_row([
            record.get("posted_at", ""),
            record.get("type", ""),
            record.get("text", "")[:200],
            record.get("tweet_id", ""),
            record.get("score", ""),
            record.get("source_url", ""),
        ])

    # === メトリクスシート ===

    def append_metrics(self, metrics: dict):
        """
        メトリクスシートにレコード追加

        Args:
            metrics: {
                "date": str,
                "followers": int,
                "avg_likes": float,
                "avg_retweets": float,
                "engagement_rate": float,
                "posted_count": int,
            }
        """
        try:
            ws = self._spreadsheet.worksheet(SHEET_METRICS)
        except gspread.exceptions.WorksheetNotFound:
            ws = self._create_metrics_sheet()

        ws.append_row([
            metrics.get("date", ""),
            metrics.get("followers", 0),
            metrics.get("avg_likes", 0),
            metrics.get("avg_retweets", 0),
            metrics.get("engagement_rate", 0),
            metrics.get("posted_count", 0),
        ])

    # === キュー管理シート（パターンB） ===

    def _get_or_create_sheet(self, name: str, creator_fn):
        """シートを取得、なければ作成"""
        try:
            return self._spreadsheet.worksheet(name)
        except gspread.exceptions.WorksheetNotFound:
            return creator_fn()

    def write_queue_items(self, items: list[dict]):
        """キュー管理シートにアイテムを書き込み（全件上書き）"""
        ws = self._get_or_create_sheet(SHEET_QUEUE, self._create_queue_sheet)

        # ヘッダー以外をクリア
        if ws.row_count > 1:
            ws.batch_clear([f"A2:J{ws.row_count}"])

        if not items:
            return

        rows = []
        for item in items:
            score = item.get("score")
            score_val = score.get("total", "") if isinstance(score, dict) else ""
            rows.append([
                item.get("status", "pending"),
                item.get("tweet_id", ""),
                f"@{item.get('author_username', '')}",
                (item.get("text", "") or "")[:100],
                item.get("likes", 0),
                item.get("added_at", ""),
                (item.get("generated_text", "") or "")[:100],
                score_val,
                item.get("source", ""),
                item.get("url", ""),
            ])

        ws.update(f"A2:J{1 + len(rows)}", rows)

    def read_queue_decisions(self) -> list[dict]:
        """キュー管理シートからクライアントの承認/拒否を読み取り"""
        ws = self._get_or_create_sheet(SHEET_QUEUE, self._create_queue_sheet)
        all_rows = ws.get_all_values()

        decisions = []
        for i, row in enumerate(all_rows):
            if i == 0:
                continue
            if len(row) < 2 or not row[1].strip():
                continue
            decisions.append({
                "row": i + 1,
                "status": row[0].strip(),
                "tweet_id": row[1].strip(),
            })
        return decisions

    # === 収集ログシート（パターンB） ===

    def append_collection_log(self, log: dict):
        """収集ログを追記"""
        ws = self._get_or_create_sheet(
            SHEET_COLLECTION_LOG, self._create_collection_log_sheet
        )
        now = datetime.now(JST).strftime("%Y/%m/%d %H:%M")
        ws.append_row([
            now,
            log.get("fetched", 0),
            log.get("filtered", 0),
            log.get("added", 0),
            log.get("skipped_dup", 0),
            log.get("error", ""),
        ])

    # === ダッシュボードシート（パターンB） ===

    def update_dashboard(self, stats: dict):
        """ダッシュボード統計を更新"""
        ws = self._get_or_create_sheet(
            SHEET_DASHBOARD, self._create_dashboard_sheet
        )
        now = datetime.now(JST).strftime("%Y/%m/%d %H:%M")
        ws.update("B2:B8", [
            [stats.get("last_collection", "—")],
            [stats.get("collected_today", 0)],
            [stats.get("pending", 0)],
            [stats.get("approved", 0)],
            [stats.get("posted_today", 0)],
            [stats.get("api_status", "OK")],
            [now],
        ])

    # === 設定シート（パターンB） ===

    def get_settings(self) -> dict:
        """設定シートから全設定を読み取り"""
        ws = self._get_or_create_sheet(SHEET_SETTINGS, self._create_settings_sheet)
        all_rows = ws.get_all_values()

        settings = {}
        for i, row in enumerate(all_rows):
            if i == 0:
                continue
            if len(row) < 2:
                continue
            key = row[0].strip()
            value = row[1].strip()
            if key:
                settings[key] = value
        return settings

    # === シート初期化 ===

    def _create_collect_sheet(self):
        """URL収集シートを作成"""
        ws = self._spreadsheet.add_worksheet(title=SHEET_COLLECT, rows=500, cols=5)
        ws.update("A1:E1", [["URL", "メモ", "ステータス", "処理日時", "ツイートID"]])
        ws.format("A1:E1", {"textFormat": {"bold": True}})
        return ws

    def _create_posted_sheet(self):
        """投稿履歴シートを作成"""
        ws = self._spreadsheet.add_worksheet(title=SHEET_POSTED, rows=1000, cols=6)
        ws.update("A1:F1", [["投稿日時", "種別", "投稿文", "Tweet ID", "スコア", "元URL"]])
        ws.format("A1:F1", {"textFormat": {"bold": True}})
        return ws

    def _create_metrics_sheet(self):
        """メトリクスシートを作成"""
        ws = self._spreadsheet.add_worksheet(title=SHEET_METRICS, rows=500, cols=6)
        ws.update("A1:F1", [["日付", "フォロワー", "平均いいね", "平均RT", "エンゲージメント率", "投稿数"]])
        ws.format("A1:F1", {"textFormat": {"bold": True}})
        return ws

    def _create_queue_sheet(self):
        """キュー管理シートを作成"""
        ws = self._spreadsheet.add_worksheet(title=SHEET_QUEUE, rows=200, cols=10)
        ws.update("A1:J1", [[
            "ステータス", "ツイートID", "著者", "ツイート本文",
            "いいね数", "収集日時", "生成テキスト", "スコア", "ソース", "URL"
        ]])
        ws.format("A1:J1", {"textFormat": {"bold": True}})
        return ws

    def _create_collection_log_sheet(self):
        """収集ログシートを作成"""
        ws = self._spreadsheet.add_worksheet(title=SHEET_COLLECTION_LOG, rows=500, cols=6)
        ws.update("A1:F1", [[
            "日時", "API取得件数", "フィルタ後", "キュー追加", "重複スキップ", "エラー"
        ]])
        ws.format("A1:F1", {"textFormat": {"bold": True}})
        return ws

    def _create_dashboard_sheet(self):
        """ダッシュボードシートを作成"""
        ws = self._spreadsheet.add_worksheet(title=SHEET_DASHBOARD, rows=20, cols=4)
        ws.update("A1:B8", [
            ["項目", "値"],
            ["最終収集日時", "—"],
            ["今日の収集件数", "0"],
            ["キュー（承認待ち）", "0"],
            ["キュー（承認済み・未投稿）", "0"],
            ["今日の投稿済み", "0"],
            ["API状態", "—"],
            ["最終更新", "—"],
        ])
        ws.format("A1:B1", {"textFormat": {"bold": True}})
        return ws

    def _create_settings_sheet(self):
        """設定シートを作成（クライアント編集可能）"""
        ws = self._spreadsheet.add_worksheet(title=SHEET_SETTINGS, rows=30, cols=3)
        ws.update("A1:C1", [["設定キー", "値", "説明"]])
        ws.update("A2:C8", [
            ["min_likes", "500", "バズツイート最低いいね数"],
            ["auto_approve", "false", "収集時の自動承認（true/false）"],
            ["max_tweets", "50", "1回の収集最大件数"],
            ["max_age_hours", "48", "ツイート最大経過時間"],
            ["daily_post_limit", "10", "1日の投稿上限"],
            ["mode", "manual_approval", "動作モード（manual_approval/semi_auto/auto）"],
            ["auto_post_min_score", "8", "自動投稿の最低スコア"],
        ])
        ws.format("A1:C1", {"textFormat": {"bold": True}})
        return ws

    def setup_sheets(self):
        """全シートを初期化（初回セットアップ用）"""
        existing = [ws.title for ws in self._spreadsheet.worksheets()]

        sheet_map = {
            SHEET_COLLECT: self._create_collect_sheet,
            SHEET_POSTED: self._create_posted_sheet,
            SHEET_METRICS: self._create_metrics_sheet,
            SHEET_QUEUE: self._create_queue_sheet,
            SHEET_COLLECTION_LOG: self._create_collection_log_sheet,
            SHEET_DASHBOARD: self._create_dashboard_sheet,
            SHEET_SETTINGS: self._create_settings_sheet,
        }

        created = []
        for name, creator in sheet_map.items():
            if name not in existing:
                creator()
                created.append(name)

        return created
