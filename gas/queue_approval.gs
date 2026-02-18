/**
 * X Auto Post System — GAS キュー承認トリガー（パターンB）
 *
 * 使い方:
 *   1. スプレッドシートの「拡張機能 > Apps Script」で開く
 *   2. このコードを貼り付け（url_trigger.gs と同じプロジェクトでOK）
 *   3. スクリプトプロパティに設定（url_trigger.gsと共通）:
 *      - GITHUB_TOKEN: GitHubのPersonal Access Token（repo権限）
 *      - GITHUB_REPO: kitayama-ai/x-quote-rt-bot
 *   4. setupQueueTriggers() を1回実行
 *
 * フロー:
 *   クライアントがキュー管理シートのA列ステータスを変更
 *   → GAS検知 → 2分後にGitHub Actions sync-queue.yml をトリガー
 *   → Python queue_sync.sync_from_sheet() でキューに反映
 */

// === 定数 ===
const QUEUE_SHEET_NAME = "キュー管理";
const QUEUE_STATUS_COL = 1;  // A列（ステータス）
const VALID_STATUSES = ["pending", "approved", "skipped"];

/**
 * キュー管理シート編集時に自動実行
 */
function onQueueEditTrigger(e) {
  const sheet = e.source.getActiveSheet();
  if (sheet.getName() !== QUEUE_SHEET_NAME) return;

  const row = e.range.getRow();
  const col = e.range.getColumn();

  // ヘッダー行はスキップ
  if (row <= 1) return;

  // A列（ステータス列）への編集のみ対象
  if (col !== QUEUE_STATUS_COL) return;

  const newStatus = sheet.getRange(row, QUEUE_STATUS_COL)
    .getValue().toString().trim().toLowerCase();

  // 有効なステータスかチェック
  if (!VALID_STATUSES.includes(newStatus)) {
    SpreadsheetApp.getUi().alert(
      "無効なステータスです。\n" +
      "使用可能: pending, approved, skipped"
    );
    return;
  }

  // バッチ処理のためスケジュール（複数行変更対応）
  scheduleQueueSync();
}

/**
 * GitHub Actions sync-queue workflow をトリガー
 */
function triggerQueueSync() {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty("GITHUB_TOKEN");
  const repo = props.getProperty("GITHUB_REPO")
    || "kitayama-ai/x-quote-rt-bot";

  if (!token) {
    Logger.log("GITHUB_TOKEN が未設定です");
    return;
  }

  const url =
    "https://api.github.com/repos/" + repo +
    "/actions/workflows/sync-queue.yml/dispatches";

  const options = {
    method: "post",
    headers: {
      "Authorization": "Bearer " + token,
      "Accept": "application/vnd.github.v3+json",
      "Content-Type": "application/json",
    },
    payload: JSON.stringify({
      ref: "main",
      inputs: {
        direction: "from_sheet",
      },
    }),
    muteHttpExceptions: true,
  };

  try {
    const response = UrlFetchApp.fetch(url, options);
    const code = response.getResponseCode();
    if (code === 204) {
      Logger.log("✅ sync-queue トリガー成功");
    } else {
      Logger.log("❌ sync-queue トリガー失敗: " +
        code + " " + response.getContentText());
    }
  } catch (e) {
    Logger.log("❌ エラー: " + e.message);
  }
}

/**
 * 同期をスケジュール（2分後にバッチ実行、重複回避）
 */
function scheduleQueueSync() {
  const triggers = ScriptApp.getProjectTriggers();
  const existing = triggers.find(
    function(t) { return t.getHandlerFunction() === "delayedQueueSync"; }
  );

  if (existing) {
    Logger.log("すでにスケジュール済み。スキップ。");
    return;
  }

  ScriptApp.newTrigger("delayedQueueSync")
    .timeBased()
    .after(2 * 60 * 1000)  // 2分後
    .create();

  Logger.log("2分後にsync-queueをスケジュール");
}

/**
 * 遅延実行されるトリガー関数
 */
function delayedQueueSync() {
  // 自分自身のトリガーを削除
  const triggers = ScriptApp.getProjectTriggers();
  triggers.filter(
    function(t) { return t.getHandlerFunction() === "delayedQueueSync"; }
  ).forEach(function(t) { ScriptApp.deleteTrigger(t); });

  // GitHub Actionsトリガー
  triggerQueueSync();
}

/**
 * 初回セットアップ: onEditトリガーを登録
 */
function setupQueueTriggers() {
  // 既存のonQueueEditトリガーを削除
  const triggers = ScriptApp.getProjectTriggers();
  triggers.filter(
    function(t) { return t.getHandlerFunction() === "onQueueEditTrigger"; }
  ).forEach(function(t) { ScriptApp.deleteTrigger(t); });

  // onEditトリガーを作成
  ScriptApp.newTrigger("onQueueEditTrigger")
    .forSpreadsheet(SpreadsheetApp.getActiveSpreadsheet())
    .onEdit()
    .create();

  Logger.log("✅ キュー承認トリガー設定完了");
}

/**
 * テスト用: 手動で同期トリガー
 */
function testQueueSync() {
  Logger.log("=== キュー同期テスト ===");
  triggerQueueSync();
}
