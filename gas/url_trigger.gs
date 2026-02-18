/**
 * X Auto Post System — GAS URL収集トリガー
 *
 * 使い方:
 *   1. スプレッドシートの「拡張機能 > Apps Script」で開く
 *   2. このコードを貼り付け
 *   3. スクリプトプロパティに設定:
 *      - GITHUB_TOKEN: GitHubのPersonal Access Token（repo権限）
 *      - GITHUB_REPO: kitayama-ai/x-quote-rt-bot
 *   4. トリガー設定: onEdit or 時間ベース（5分ごと）
 *
 * フロー:
 *   スプシにURL追加 → GASがGitHub Actions workflow_dispatch → import-urls実行
 */

// === 定数 ===
const SHEET_NAME = "URL収集";
const STATUS_COL = 3;  // C列（ステータス）
const URL_COL = 1;     // A列（URL）

/**
 * スプシ編集時に自動実行（onEditトリガー）
 * A列にURLが貼られ、C列が空のとき、GitHub Actionsをトリガー
 */
function onEditTrigger(e) {
  const sheet = e.source.getActiveSheet();

  // URL収集シートのみ対象
  if (sheet.getName() !== SHEET_NAME) return;

  const row = e.range.getRow();
  const col = e.range.getColumn();

  // ヘッダー行はスキップ
  if (row <= 1) return;

  // A列への編集のみ対象
  if (col !== URL_COL) return;

  const url = sheet.getRange(row, URL_COL).getValue().toString().trim();
  const status = sheet.getRange(row, STATUS_COL).getValue().toString().trim();

  // URLが空 or すでに処理済みならスキップ
  if (!url || status !== "") return;

  // ツイートURLの簡易チェック
  if (!isValidTweetUrl(url)) {
    sheet.getRange(row, STATUS_COL).setValue("無効URL");
    return;
  }

  // GitHub Actionsトリガーは即時実行せず、バッチ処理
  // 複数URL同時貼り付けに対応するため、5分後にトリガー
  scheduleImport();
}

/**
 * 定期実行: 未処理URLがあればGitHub Actionsをトリガー
 * ※ 時間ベーストリガー（5分ごと）で使用
 */
function checkAndTrigger() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  if (!sheet) return;

  const lastRow = sheet.getLastRow();
  if (lastRow <= 1) return;

  // 未処理URLがあるかチェック
  const data = sheet.getRange(2, 1, lastRow - 1, 3).getValues();
  const pendingCount = data.filter(row => {
    const url = row[0].toString().trim();
    const status = row[2].toString().trim();
    return url !== "" && status === "" && isValidTweetUrl(url);
  }).length;

  if (pendingCount === 0) return;

  Logger.log(`未処理URL: ${pendingCount}件 → GitHub Actionsをトリガー`);
  triggerGitHubActions();
}

/**
 * GitHub Actions の workflow_dispatch をトリガー
 */
function triggerGitHubActions() {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty("GITHUB_TOKEN");
  const repo = props.getProperty("GITHUB_REPO") || "kitayama-ai/x-quote-rt-bot";

  if (!token) {
    Logger.log("GITHUB_TOKEN が未設定です");
    return;
  }

  const url = `https://api.github.com/repos/${repo}/actions/workflows/import-urls.yml/dispatches`;

  const options = {
    method: "post",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Accept": "application/vnd.github.v3+json",
      "Content-Type": "application/json",
    },
    payload: JSON.stringify({
      ref: "main",
      inputs: {
        account: "1",
        auto_approve: "false",
      }
    }),
    muteHttpExceptions: true,
  };

  try {
    const response = UrlFetchApp.fetch(url, options);
    const code = response.getResponseCode();
    if (code === 204) {
      Logger.log("✅ GitHub Actions トリガー成功");
    } else {
      Logger.log(`❌ GitHub Actions トリガー失敗: ${code} ${response.getContentText()}`);
    }
  } catch (e) {
    Logger.log(`❌ エラー: ${e.message}`);
  }
}

/**
 * インポートをスケジュール（5分後に実行、重複回避）
 */
function scheduleImport() {
  // 既存のトリガーを確認
  const triggers = ScriptApp.getProjectTriggers();
  const existing = triggers.find(t => t.getHandlerFunction() === "delayedTrigger");

  if (existing) {
    Logger.log("すでにスケジュール済み。スキップ。");
    return;
  }

  // 5分後にトリガー
  ScriptApp.newTrigger("delayedTrigger")
    .timeBased()
    .after(5 * 60 * 1000)  // 5分後
    .create();

  Logger.log("5分後にGitHub Actionsトリガーをスケジュール");
}

/**
 * 遅延実行されるトリガー関数
 */
function delayedTrigger() {
  // 自分自身のトリガーを削除
  const triggers = ScriptApp.getProjectTriggers();
  triggers.filter(t => t.getHandlerFunction() === "delayedTrigger")
    .forEach(t => ScriptApp.deleteTrigger(t));

  // GitHub Actionsトリガー
  triggerGitHubActions();
}

/**
 * ツイートURLの簡易バリデーション
 */
function isValidTweetUrl(url) {
  const patterns = [
    /https?:\/\/(x|twitter)\.com\/\w+\/status\/\d+/,
    /https?:\/\/mobile\.(x|twitter)\.com\/\w+\/status\/\d+/,
    /https?:\/\/(vx|fx)twitter\.com\/\w+\/status\/\d+/,
  ];
  return patterns.some(p => p.test(url));
}

/**
 * 手動実行: テスト用
 */
function testTrigger() {
  Logger.log("=== テスト実行 ===");
  checkAndTrigger();
}

/**
 * 初回セットアップ: onEditトリガーを登録
 */
function setupTriggers() {
  // 既存のonEditトリガーを削除
  const triggers = ScriptApp.getProjectTriggers();
  triggers.filter(t => t.getHandlerFunction() === "onEditTrigger")
    .forEach(t => ScriptApp.deleteTrigger(t));

  // onEditトリガーを作成
  ScriptApp.newTrigger("onEditTrigger")
    .forSpreadsheet(SpreadsheetApp.getActiveSpreadsheet())
    .onEdit()
    .create();

  // 5分ごとの定期チェックも作成
  ScriptApp.newTrigger("checkAndTrigger")
    .timeBased()
    .everyMinutes(5)
    .create();

  Logger.log("✅ トリガー設定完了");
}
