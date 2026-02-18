# X 3アカウント自動運用システム

> Python + GitHub Actions + Gemini API + X API (Free tier) + Discord Webhook

AIを使ったX 3アカウントの自動運用で、知見の醸成とマネタイズを最大化する。

## 技術スタック

| レイヤー   | 技術                 | 理由                             |
| ---------- | -------------------- | -------------------------------- |
| 実行環境   | GitHub Actions       | 無料、cron対応、シークレット管理 |
| 言語       | Python 3.11+         | 既存コード資産との互換性         |
| AI         | Gemini 2.5 Flash API | 無料枠大、高速、日本語◎          |
| SNS API    | X API v2 (Free tier) | 投稿は無料                       |
| データ保存 | Google Sheets        | 無料、可視性◎                    |
| 通知       | Discord Webhook      | 無料、プライベート運用に最適     |

## クイックスタート

```bash
# 1. 環境変数を設定
cp .env.example .env
# → .env を編集して各APIキーを入力

# 2. 依存関係をインストール
pip install -r requirements.txt

# 3. 投稿案を生成（ドライラン）
python -m src.main generate --account 1 --dry-run

# 4. Discord通知テスト
python -m src.main notify-test

# 5. 投稿（手動承認モード）
python -m src.main generate --account 1
```

## 段階的自動化

| フェーズ | 期間    | 自動化レベル                      |
| -------- | ------- | --------------------------------- |
| Phase 1  | 1-2週目 | 生成は自動、投稿は手動承認        |
| Phase 2  | 3-4週目 | スコア8+は自動投稿、7以下は要承認 |
| Phase 3  | 5週目〜 | 安全チェック通過で全自動          |

## アカウント構成

| #   | テーマ                  | ペルソナ                 | 状態           |
| --- | ----------------------- | ------------------------ | -------------- |
| ①   | AIエージェント・自動化  | レン (@ren_aiautomation) | ★ まずここから |
| ②   | AIツール紹介・レビュー  | TBD                      | Phase B で追加 |
| ③   | LLM・テキスト生成AI入門 | TBD                      | Phase C で追加 |

## 月間コスト

- アカウント①のみ: **月100〜300円**
- 3アカウント運用: **月300〜1,250円**
