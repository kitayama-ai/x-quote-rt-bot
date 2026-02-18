"""
X Auto Post System — Google Sheets クライアント

スプレッドシートからURL収集シートの読み書きを行う。
パターンAの手動収集で使用。
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

# シート名
SHEET_COLLECT = "URL収集"
SHEET_POSTED = "投稿履歴"
SHEET_METRICS = "メトリクス"


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

    def setup_sheets(self):
        """全シートを初期化（初回セットアップ用）"""
        existing = [ws.title for ws in self._spreadsheet.worksheets()]

        created = []
        if SHEET_COLLECT not in existing:
            self._create_collect_sheet()
            created.append(SHEET_COLLECT)
        if SHEET_POSTED not in existing:
            self._create_posted_sheet()
            created.append(SHEET_POSTED)
        if SHEET_METRICS not in existing:
            self._create_metrics_sheet()
            created.append(SHEET_METRICS)

        return created
