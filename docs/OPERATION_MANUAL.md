# 海外AIバズ引用RT自動化ツール — 操作マニュアル

> バージョン: v1.1 / 最終更新: 2026-02-22

---

## このツールで何ができるか

海外のAI系バズツイートを自動で見つけて、日本語コメントをAIが生成し、Xに引用RTとして投稿します。

```
① 海外バズツイートを自動収集（毎朝6時）
        ↓
② AIが日本語コメントを自動生成
        ↓
③ スケジュールに従ってXに自動投稿（1日最大10回）
```

**基本的にすべて自動で動きます。**
手動操作が必要なのは「特定のツイートを指定したいとき」と「ダッシュボード確認」だけです。

---

## 管理画面（ダッシュボード）

**URL: https://isai-11f7b.web.app**

ここでキューの状態・投稿件数を確認できます。

| 表示項目 | 意味 |
|---|---|
| pending | 収集済み・承認待ちのツイート数 |
| approved | 承認済み（投稿待ち）のツイート数 |
| posted_today | 今日の投稿件数 |
| posted_total | 累計投稿件数 |

---

## 自動実行スケジュール（GitHub Actionsで動作）

設定済みのため、**何もしなくても以下が自動で動きます：**

| 時刻（JST） | 動作内容 |
|---|---|
| 毎朝 6:00 | バズツイート自動収集 |
| 毎朝 6:30 | 収集したツイートへのAIコメント生成 |
| 7:00 / 8:30 / 10:15 / 12:00 / 14:15 / 16:00 / 18:00 / 19:45 / 21:00 / 22:30 | 引用RT自動投稿（1日最大10回） |
| 毎晩 23:00 | エンゲージメント計測 |
| 毎週月曜 | 週次レポート生成 |

---

## よく使う操作

### 1. 特定のツイートを引用RTしたい

引用RTしたいツイートのURLをコピーし、ターミナルで以下を実行：

```bash
cd /path/to/x-quote-rt-bot
source .venv/bin/activate
python3 tools/add_tweet.py https://x.com/username/status/XXXXXXXXX
python3 -m src.main curate --account 1
python3 -m src.main curate-post --account 1
```

### 2. 今すぐ収集・投稿を手動実行したい

GitHub Actions から手動実行できます：

1. https://github.com/kitayama-ai/x-quote-rt-bot/actions を開く
2. 左メニューから実行したいワークフローを選ぶ
3. 右上の「Run workflow」ボタンをクリック

| ワークフロー名 | 用途 |
|---|---|
| Daily Collect | バズツイートを今すぐ収集 |
| Daily Curate | AIコメントを今すぐ生成 |
| Scheduled Curate Post | 今すぐ投稿を実行 |

### 3. ダッシュボードを最新データに更新したい

ターミナルで以下を実行：

```bash
cd /path/to/x-quote-rt-bot
python3 -m src.main export-dashboard --account 1
firebase deploy --only hosting
```

---

## トラブルシューティング

### 投稿が止まっている

**確認場所:** https://github.com/kitayama-ai/x-quote-rt-bot/actions

赤い✗が出ているワークフローをクリックして、エラー内容を確認してください。

よくある原因：

| エラー | 原因 | 対処 |
|---|---|---|
| 403 Forbidden | X APIスパム判定 | 30分待って再実行 |
| 402 Payment Required | X APIクレジット残高ゼロ | console.x.com → Billing でクレジット購入 |
| 401 Unauthorized | アクセストークン期限切れ | X Developer ConsoleでTokenを再生成し、GitHub Secretsを更新 |

### GitHub Secretsの更新方法

1. https://github.com/kitayama-ai/x-quote-rt-bot/settings/secrets/actions を開く
2. 更新したいSecretをクリック → 新しい値を入力 → 「Update secret」

---

## APIキー管理

### X API（X Developer Console）

- URL: https://developer.x.com/en/portal/dashboard
- アプリ名: 「海外バズ引リツ」
- キー更新: Apps → 対象アプリ → Keys and Tokens → Regenerate

### Gemini API（Google AI Studio）

- URL: https://aistudio.google.com/apikey
- キー更新: 「Create API key」で新規作成し、GitHub Secretsの `GEMINI_API_KEY` を更新

### X APIクレジット残高確認

- URL: https://console.x.com → Billing → Credits
- 残高がゼロになると投稿が止まります（目安: 月$3〜5）

---

## コスト目安（月額）

| 項目 | 目安 |
|---|---|
| X API（Pay Per Use） | 約$3〜5（450〜750円） |
| Gemini API | ほぼ無料（$0〜0.50） |
| GitHub Actions | 無料枠内 |
| Firebase Hosting | 無料枠内 |
| **合計** | **約$3〜5/月（450〜750円）** |

---

## 設定変更

### いいね数の閾値を変える（収集条件）

`config/quote_rt_rules.json` を開いて `min_likes` の値を変更：

```json
"buzz_thresholds": {
  "min_likes": 500,   ← ここを変える（例: 300 にすると収集が増える）
  ...
}
```

### 1日の投稿数を変える

`config/accounts.json` を開いて変更：

```json
"posting_rules": {
  "daily_quote_rt_posts": 7   ← 引用RTの上限（最大10）
}
```

変更後はGitHubにプッシュすれば自動で反映されます。

---

## 問い合わせ先

ツールに関する質問は担当開発者までお問い合わせください。
