# X API 開発ガイド（トラブルシューティング込み）

> X Developer Portal + Firebase Auth 連携で躓いたポイントと解決策

## 1. X Developer Portal 初期設定

### 必要な準備物
- X Developer アカウント（developer.x.com）
- 有効な利用規約URL（`https://your-app.web.app/terms.html`）
- 有効なプライバシーポリシーURL（`https://your-app.web.app/privacy.html`）
- Website URL（`https://your-app.web.app`）

### アプリ認証設定の手順
1. developer.x.com → アプリ → 対象アプリを選択
2. 右パネル「ユーザー認証設定」→「セットアップ」
3. 以下を設定：
   - **アプリの権限**: 「読み取りと書き込み」（投稿するなら必須）
   - **アプリの種類**: 「ウェブアプリ、自動化アプリまたはボット」
   - **Callback URI**: Firebase用 `https://<project-id>.firebaseapp.com/__/auth/handler`
   - **Website URL**: `https://your-app.web.app`
   - **利用規約URL**: 実在するページのURL
   - **ポリシーURL**: 実在するページのURL
4. 「変更する」をクリック

### ⚠️ よくあるトラブル

#### フォームが保存されない
- **原因**: 利用規約/ポリシーURLがplaceholder（`https://`）のまま
- **解決**: Firebase Hostingに簡単なterms.html/privacy.htmlを作成してデプロイ

#### 「組織名」フィールドにURLを求められる
- **原因**: 日本語UIのバグ。ラベルが「組織名」だがURL入力欄
- **解決**: URLを入力する（ポートフォリオURLなど）

#### 設定が毎回リセットされる
- **原因**: 必須フィールドが不完全で保存が実際には失敗している
- **解決**: 全フィールドを正しく埋めてから保存

---

## 2. Firebase Authentication × Twitter 連携

### Firebase Console 設定
1. Firebase Console → Authentication → Sign-in method
2. 「新しいプロバイダを追加」→ 「Twitter」
3. X Developer Portal の **OAuth 1.0 API Key** と **API Key Secret** を入力
4. コールバックURL（自動表示）をコピー → X Developer Portalに登録
5. 保存

### OAuth 1.0a vs 2.0
- Firebase Auth は **OAuth 1.0a** を使用
- OAuth 2.0 (PKCE) はアプリ独自認証フロー用
- 間違えてOAuth 2.0のキーを使わないこと

### Xログイン時の注意
- `user.email` が **null** になることがある（X側でメール非公開設定の場合）
- 管理者判定を `ADMIN_EMAILS.includes(user.email)` で行う場合、null安全に
- `user.displayName` はXの表示名が入る
- `user.photoURL` はXのアイコンURL

---

## 3. API キー管理

### キーの種類と用途
| キー | Firebase Auth | API投稿 | API読み取り |
|------|:---:|:---:|:---:|
| API Key (Consumer Key) | ✅ | ✅ | - |
| API Key Secret | ✅ | ✅ | - |
| Bearer Token | - | - | ✅ |
| Access Token | - | ✅ | ✅ |
| Access Token Secret | - | ✅ | ✅ |

### 重要な注意点
- **Access Token は生成時に一度だけ表示** → 即コピー必須
- **権限変更後はAccess Token再生成が必要**（読み取り→読み書きに変更した場合等）
- Bearer Token は「取り込み」で既存のものを表示可能

---

## 4. Firebase Hosting で利用規約・ポリシーページ

### なぜ必要？
X Developer Portal の認証設定で有効なURLが必須。`https://example.com` では不十分な場合がある。

### 作成方法
```bash
# public/ に terms.html と privacy.html を作成
# firebase deploy --only hosting でデプロイ
# URL例: https://isai-11f7b.web.app/terms.html
```

---

## 5. エラーコード対応表

| Firebase Auth エラー | 意味 | 対処 |
|---------------------|------|------|
| `auth/operation-not-allowed` | プロバイダー未有効化 | Firebase Console で有効化 |
| `auth/popup-blocked` | ブラウザがポップアップブロック | signInWithRedirect にフォールバック |
| `auth/account-exists-with-different-credential` | 別方法で既にログイン済み | 最初に使った方法でログイン |
| `auth/network-request-failed` | ネットワークエラー | 接続確認 |
| `auth/popup-closed-by-user` | ユーザーがキャンセル | 無視（エラー表示不要） |
| `auth/cancelled-popup-request` | 複数ポップアップ | 無視 |
