# X 海外AIバズ引用RT自動化ツール — 操作マニュアル

> **バージョン**: v1.0
> **最終更新**: 2026-02-22
> **対象**: ターミナル操作が可能な方

---

## 目次

1. [ツール概要](#1-ツール概要)
2. [初期セットアップ](#2-初期セットアップ)
3. [基本的な使い方（日常運用）](#3-基本的な使い方日常運用)
4. [コマンド一覧](#4-コマンド一覧)
5. [運用パターン](#5-運用パターン)
6. [Google Sheets 連携](#6-google-sheets-連携)
7. [設定のカスタマイズ](#7-設定のカスタマイズ)
8. [トラブルシューティング](#8-トラブルシューティング)
9. [コスト目安](#9-コスト目安)
10. [GitHub Actions（自動化）](#10-github-actions自動化)

---

## 1. ツール概要

### 何ができるか

海外のAI関連バズツイートを自動収集し、日本語の引用RTコメントをAI（Gemini）で生成、Xに投稿するツールです。

```
海外バズツイート収集 → AIでコメント生成 → 安全チェック → X投稿
```

### 主な機能

| 機能 | 説明 |
|---|---|
| バズツイート自動収集 | X API v2 で海外AIインフルエンサーのバズツイートを自動収集 |
| AIコメント生成 | Gemini でツイートを翻訳・要約し、5種類のテンプレートで引用RTコメントを生成 |
| 安全チェック | NGワード検出、スコアリング、重複検出を自動で実施 |
| Google Sheets連携 | キュー管理・設定変更をスプレッドシートから操作可能 |
| Discord通知 | 収集・生成・投稿の結果をDiscordに自動通知 |
| PDCA | 週次レポートで投稿パフォーマンスを分析・改善 |

### テンプレート（5種類）

| ID | 名前 | 説明 |
|---|---|---|
| translate_comment | 翻訳+自分コメント型 | 翻訳しつつ自分の意見を添える |
| summary_points | 要点まとめ型 | ポイントを箇条書きで整理 |
| question_prompt | 問題提起型 | 読者に問いかける形式 |
| practice_report | 実践レポート型 | 実際に試した体験として書く |
| breaking_news | 速報型 | ニュース速報風の形式 |

---

## 2. 初期セットアップ

### 必要なもの

- Python 3.11以上
- X Developer アカウント（Pay Per Use プラン以上）
- Gemini API キー
- （任意）Google Sheets サービスアカウント
- （任意）Discord Webhook URL

### 手順

#### 2-1. リポジトリのクローン

```bash
git clone https://github.com/kitayama-ai/x-quote-rt-bot.git
cd x-quote-rt-bot
```

#### 2-2. 仮想環境の作成と依存パッケージのインストール

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### 2-3. 環境変数の設定

`.env.example` を参考に `.env` ファイルを作成してください。

```bash
cp .env.example .env
```

`.env` に以下を設定します：

```env
# === 必須 ===
# X API Keys（X Developer Console → アプリ → OAuth 1.0 Keys）
X_API_KEY=your_consumer_key
X_API_SECRET=your_consumer_secret
TWITTER_BEARER_TOKEN=your_bearer_token

# アカウント1のアクセストークン
X_ACCOUNT_1_ACCESS_TOKEN=your_access_token
X_ACCOUNT_1_ACCESS_SECRET=your_access_token_secret

# Gemini API Key（Google AI Studio で取得）
GEMINI_API_KEY=your_gemini_api_key

# === 任意 ===
# Discord Webhooks
DISCORD_WEBHOOK_X_ACCOUNT_1=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_GENERAL=https://discord.com/api/webhooks/...

# Google Sheets
SPREADSHEET_ID=your_spreadsheet_id
GOOGLE_CREDENTIALS_BASE64=base64_encoded_service_account_json

# Firebase
FIREBASE_PROJECT_ID=your_project_id

# 動作モード: manual_approval / semi_auto / auto
MODE=manual_approval
```

#### 2-4. 動作確認

```bash
# 認証テスト
python3 -c "
from src.config import Config
from src.post.x_poster import XPoster
config = Config()
poster = XPoster(config)
print(poster.verify_credentials())
"
```

`{'id': ..., 'name': '...', 'username': '...'}` が表示されれば成功です。

---

## 3. 基本的な使い方（日常運用）

### 最もシンプルな運用フロー

```
Step 1: バズツイートを収集
Step 2: 収集結果を確認・承認
Step 3: AIで引用RTコメントを生成
Step 4: 確認して投稿
```

#### Step 1: バズツイートを収集

```bash
python3 -m src.main collect --auto-approve --min-likes 500
```

- `--auto-approve`: 収集したツイートを自動承認（手動確認を省略）
- `--min-likes 500`: いいね500以上のツイートのみ収集
- `--dry-run`: 追加せずに結果だけ確認したい場合

#### Step 2: キューの状態を確認

```bash
python3 tools/add_tweet.py --status
```

出力例:
```
📊 キューの統計:
  pending (承認待ち): 3件
  approved (承認済み): 5件
  generated (生成済み): 0件
  posted (投稿済み): 12件
```

手動で承認する場合：
```bash
# 全件承認
python3 tools/add_tweet.py --approve-all

# 個別に承認
python3 tools/add_tweet.py --approve TWEET_ID
```

#### Step 3: AIで引用RTコメントを生成

```bash
python3 -m src.main curate --account 1
```

- 承認済みツイートに対してGeminiが引用RTコメントを自動生成
- スコアリング（5点以上で合格）と安全チェックを自動実施
- `--dry-run`: 生成だけして保存しない場合

#### Step 4: 引用RT投稿

```bash
python3 -m src.main curate-post --account 1
```

- 生成済みの引用RTコメントを実際にXに投稿
- 安全チェック最終確認 → 投稿 → Discord通知

### 手動でURLを追加する場合

特定のツイートを引用RTしたい場合：

```bash
python3 tools/add_tweet.py https://x.com/username/status/1234567890
```

---

## 4. コマンド一覧

### 収集・キュー管理

| コマンド | 説明 |
|---|---|
| `collect` | バズツイートを自動収集（X API v2） |
| `import-urls` | Google Sheetsからツイート URL を一括インポート |
| `tools/add_tweet.py <URL>` | 手動でツイートURLを追加 |
| `tools/add_tweet.py --status` | キューの状態を確認 |
| `tools/add_tweet.py --list` | キュー内のツイートを一覧表示 |
| `tools/add_tweet.py --approve-all` | 全件一括承認 |

### 生成・投稿

| コマンド | 説明 |
|---|---|
| `curate --account 1` | 承認済みツイートの引用RTコメントを生成 |
| `curate-post --account 1` | 生成済みの引用RTを投稿 |
| `generate --account 1` | オリジナル投稿を生成 |
| `post --account 1` | 予約投稿を実行 |

### 分析・レポート

| コマンド | 説明 |
|---|---|
| `metrics --account 1` | エンゲージメントメトリクスを収集 |
| `weekly-pdca --account 1` | 週次PDCAレポートを生成 |
| `selection-pdca` | 選定PDCAを実行（承認率の分析） |
| `analyze-persona --account 1` | アカウントの文体を分析 |

### 同期・設定

| コマンド | 説明 |
|---|---|
| `setup-sheets --account 1` | Google Sheetsの初期セットアップ |
| `sync-queue --direction full` | キュー ↔ Sheets 双方向同期 |
| `sync-settings` | Sheetsから設定を読み込み |
| `preferences` | 選定プリファレンスを表示 |
| `notify-test` | Discord通知テスト |

### 全コマンド共通オプション

| オプション | 説明 |
|---|---|
| `--account 1` (`-a 1`) | アカウント番号（デフォルト: 1） |
| `--dry-run` | 実行せずに結果だけ確認 |
| `--help` | ヘルプを表示 |

---

## 5. 運用パターン

### パターン A: 手動承認型（推奨初期設定）

最も安全な運用方法です。投稿前に必ず人間が確認します。

```
MODE=manual_approval
```

```
毎日の流れ:
  朝: collect で収集 → Sheets or Discord で確認 → 承認
  昼: curate で生成 → 確認 → curate-post で投稿
  夜: metrics で結果確認
```

### パターン B: 半自動型

スコア8点以上の投稿は自動投稿、それ以下は手動承認。

```
MODE=semi_auto
```

### パターン C: 全自動型

安全チェック通過で全自動投稿。GitHub Actions で完全自動化。

```
MODE=auto
```

---

## 6. Google Sheets 連携

### セットアップ

1. Google Cloud Console でサービスアカウントを作成
2. JSON キーをダウンロードし、Base64 エンコード:
   ```bash
   base64 -i credentials.json | tr -d '\n'
   ```
3. `.env` に設定:
   ```env
   GOOGLE_CREDENTIALS_BASE64=base64_encoded_value
   SPREADSHEET_ID=your_spreadsheet_id
   ```
4. 初期セットアップ:
   ```bash
   python3 -m src.main setup-sheets --account 1
   ```

### シート構成

| シート名 | 用途 |
|---|---|
| キュー管理 | 収集したツイートの承認/スキップ操作 |
| 収集ログ | 収集結果の履歴 |
| ダッシュボード | 統計情報 |
| 設定 | min_likes等の設定値を変更可能 |
| 選定プリファレンス | トピック優先度・NGワード等 |
| 投稿履歴 | 投稿済みツイートの記録 |

### 同期コマンド

```bash
# 完全同期（双方向）
python3 -m src.main sync-queue --direction full --account 1

# Sheets → キュー（承認操作の反映）
python3 -m src.main sync-queue --direction from_sheet --account 1

# キュー → Sheets（収集結果の反映）
python3 -m src.main sync-queue --direction to_sheet --account 1
```

---

## 7. 設定のカスタマイズ

### アカウント設定

`config/accounts.json` で変更できます：

```json
{
  "accounts": [{
    "id": "account_1",
    "name": "アカウント名",
    "handle": "@your_handle",
    "theme": "AI・自動化",
    "schedule": {
      "morning": { "base_hour": 7 },
      "noon": { "base_hour": 12 },
      "evening": { "base_hour": 21 }
    },
    "posting_rules": {
      "daily_posts": 10,
      "daily_original_posts": 3,
      "daily_quote_rt_posts": 7
    }
  }]
}
```

### 安全ルール

`config/safety_rules.json` でNGワードやルールを変更：

```json
{
  "ng_words": {
    "scam_related": ["稼げる", "必ず儲かる", "元本保証"],
    "company_names": ["cyan", "サイアン"],
    "personal": ["北田", "yamato"]
  },
  "content_rules": {
    "max_hashtags": 3,
    "max_emojis": 3,
    "min_length": 40,
    "max_length": 280
  }
}
```

### 引用RTルール

`config/quote_rt_rules.json` で引用RTの条件を変更：

```json
{
  "quote_rt": {
    "min_comment_length": 30,
    "max_same_source_daily": 1
  },
  "buzz_thresholds": {
    "min_likes": 500,
    "min_retweets": 100,
    "max_age_hours": 48,
    "lang": "en"
  }
}
```

### 監視対象アカウント

`config/target_accounts.json` で監視アカウントを追加・削除：

```json
{
  "accounts": [
    {
      "username": "sama",
      "name": "Sam Altman",
      "category": "AI Leaders",
      "priority": "high"
    }
  ]
}
```

---

## 8. トラブルシューティング

### 403 Forbidden（投稿時）

**原因**: 短時間に同じツイートへの引用RTを連投するとスパム判定される
**対策**: 1回/時間以上の間隔を空ける。別のツイートIDで再試行。

### 402 Payment Required

**原因**: X APIのクレジット残高がゼロ
**対策**: console.x.com → Billing → Credits → クレジットを購入

### 401 Unauthorized

**原因**: アクセストークンが無効
**対策**:
1. console.x.com → Apps → 対象アプリ → Access Token を Regenerate
2. `.env` のトークンを更新

### Gemini API エラー

**原因**: GEMINI_API_KEY が未設定 or クォータ超過
**対策**: Google AI Studio でAPIキーを確認・再生成

### キューが空

**原因**: 承認済みツイートがない
**対策**:
```bash
python3 tools/add_tweet.py --approve-all
```

---

## 9. コスト目安

### X API（Pay Per Use）

| 操作 | コスト |
|---|---|
| ツイート検索 (1リクエスト) | $0.005 |
| ツイート投稿 | $0.005 |
| 1日10ツイート運用 | 約$0.10/日 |
| **月額目安** | **約$3（約450円）** |

### Gemini API

| 操作 | コスト |
|---|---|
| gemini-2.5-flash 1リクエスト | ほぼ無料 |
| **月額目安** | **約$0〜0.50** |

### 合計月額目安

```
基本運用: 約$3〜5/月（450〜750円）
```

---

## 10. GitHub Actions（自動化）

GitHub Actions を使うと、毎日自動で収集→生成→投稿まで実行できます。

### 設定手順

1. GitHub リポジトリの Settings → Secrets and variables → Actions
2. 以下のシークレットを追加:

| Secret名 | 値 |
|---|---|
| `X_API_KEY` | Consumer Key |
| `X_API_SECRET` | Consumer Secret |
| `X_ACCOUNT_1_ACCESS_TOKEN` | Access Token |
| `X_ACCOUNT_1_ACCESS_SECRET` | Access Token Secret |
| `TWITTER_BEARER_TOKEN` | Bearer Token |
| `GEMINI_API_KEY` | Gemini API Key |
| `DISCORD_WEBHOOK_GENERAL` | Discord Webhook URL |
| `GOOGLE_CREDENTIALS_BASE64` | Google Sheets認証情報（Base64） |
| `SPREADSHEET_ID` | スプレッドシートID |

### ワークフロー（自動実行スケジュール）

| ワークフロー | 実行時間 | 内容 |
|---|---|---|
| daily-collect | 毎日 6:00 JST | バズツイート収集 |
| daily-generate | 毎日 6:30 JST | オリジナル投稿生成 |
| daily-curate | 毎日 6:30 JST | 引用RTコメント生成 |
| scheduled-post | 7:00/12:00/21:00 JST | 予約投稿実行 |
| daily-metrics | 毎日 23:00 JST | メトリクス収集 |
| weekly-pdca | 毎週月曜 | 週次PDCAレポート |

### 手動実行

GitHub → Actions → 対象ワークフロー → Run workflow

---

## 付録: クイックスタート（5分で始める）

```bash
# 1. クローン & セットアップ
git clone https://github.com/kitayama-ai/x-quote-rt-bot.git
cd x-quote-rt-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. .env を設定（上記「初期セットアップ」を参照）

# 3. 認証テスト
python3 -c "from src.config import Config; from src.post.x_poster import XPoster; print(XPoster(Config()).verify_credentials())"

# 4. バズツイート収集（ドライラン）
python3 -m src.main collect --dry-run --min-likes 500

# 5. 手動でURL追加 → 承認 → 生成 → 投稿
python3 tools/add_tweet.py https://x.com/example/status/123456
python3 tools/add_tweet.py --approve-all
python3 -m src.main curate --account 1
python3 -m src.main curate-post --account 1
```

---

> このツールに関する質問は担当開発者までお問い合わせください。
