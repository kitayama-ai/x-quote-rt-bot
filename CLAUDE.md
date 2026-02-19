# x-auto-post-system プロジェクト設定

## プロジェクト概要
X（旧Twitter）の海外バズツイートを自動収集し、引用RTとして投稿するシステム。
Firebase Hosting でクライアント向け管理ダッシュボードを提供。

## Firebase 設定
- プロジェクトID: `isai-11f7b`
- Hosting URL: `https://isai-11f7b.web.app`
- Firestore: users / api_keys コレクション
- Auth: Google + Twitter プロバイダー
- 管理者メール: `dbeitian@gmail.com`

## デプロイ
```bash
# Hostingのみ
firebase deploy --only hosting

# Firestoreルールのみ
firebase deploy --only firestore

# GitHub Actions で自動デプロイ（main push時）
# FIREBASE_TOKEN は GitHub Secrets に設定済み
```

## ファイル構成（ダッシュボード）
```
public/
  index.html        # メインダッシュボード（CSS/HTML/JS一体型）
  terms.html         # 利用規約ページ
  privacy.html       # プライバシーポリシーページ
  dashboard-data.json # ダッシュボードデータ（静的）
firestore.rules      # Firestoreセキュリティルール
firebase.json        # Firebase設定
```

## X API 開発の重要な注意点

### X Developer Portal の設定落とし穴
1. **利用規約・ポリシーURL必須**: placeholder（`https://`）のままだとフォームが保存されない。実在するURLを入れること
2. **「組織名」フィールドのバグ**: 日本語UIで「組織名」と表示されるがURL入力欄として動作する場合がある。上がURL欄、下がテキスト欄
3. **設定が保存されない場合**: 全フィールドに有効値が入っているか確認。Incognitoモードも試す
4. **メールリクエストONにはToS/Privacy URLが必要**

### Firebase × Twitter Auth
- Firebase Console → Authentication → Sign-in method → Twitter を有効化
- **OAuth 1.0a** の API Key / Secret を使う（OAuth 2.0ではない）
- コールバックURL: `https://isai-11f7b.firebaseapp.com/__/auth/handler`
- Xログイン時 `user.email` が null になりうる → null 安全な処理が必要

### API キーの種類
| キー | 用途 |
|------|------|
| API Key (Consumer Key) | OAuth 1.0a / Firebase Auth |
| API Key Secret | OAuth 1.0a / Firebase Auth |
| Bearer Token | App-only認証（読み取り専用） |
| Access Token + Secret | ユーザー認証（投稿に必要） |

### エラーハンドリング
- `auth/operation-not-allowed` → プロバイダー未有効化
- `auth/popup-blocked` → signInWithRedirect にフォールバック
- Access Token 生成後は一度しか表示されない → 必ず即コピー
- 権限変更後はAccess Token再生成が必要

## コーディング規約
- ダッシュボードは単一HTMLファイル（index.html）にCSS/JS含む
- デザイン: OLED ダークテーマ、Fira Code + Inter + Noto Sans JP
- SVGアイコン使用（絵文字は使わない）
- Firebase SDK: compat v10.8.0
