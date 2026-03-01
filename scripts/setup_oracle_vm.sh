#!/bin/bash
# =============================================================================
# Oracle Cloud Free Tier VM セットアップスクリプト
# Ubuntu 22.04 / 24.04 対応
#
# 使い方:
#   1. Oracle Cloud で Always Free VM を作成し SSH 接続
#   2. このスクリプトを VM 上で実行:
#      curl -fsSL https://raw.githubusercontent.com/<YOUR_REPO>/main/scripts/setup_oracle_vm.sh | bash
#      または: bash setup_oracle_vm.sh
#
# 実行後に対話式で以下を入力:
#   - FIREBASE_CREDENTIALS_BASE64 (GitHub Secrets から貼り付け)
#   - DATA_UID (例: YZnBvrP5emdmuWthTZZyS1YhTf62)
#   - GitHub の Personal Access Token (repo commit 用)
# =============================================================================
set -euo pipefail

REPO_URL="https://github.com/kitayama-ai/x-quote-rt-bot.git"
REPO_DIR="$HOME/x-quote-rt-bot"
LOG_DIR="/var/log/xbot"
PYTHON="python3"

echo "╔══════════════════════════════════════════════╗"
echo "║  X Quote RT Bot — Oracle VM セットアップ     ║"
echo "╚══════════════════════════════════════════════╝"

# ── 1. システム依存パッケージ ──────────────────────
echo ""
echo "📦 [1/6] パッケージをインストール中..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv git curl

# Python バージョン確認
echo "   Python: $(python3 --version)"

# ── 2. リポジトリ取得 ──────────────────────────────
echo ""
echo "📥 [2/6] リポジトリをクローン中..."
if [ -d "$REPO_DIR" ]; then
    echo "   既存のディレクトリが見つかりました。git pull します"
    cd "$REPO_DIR" && git pull
else
    git clone "$REPO_URL" "$REPO_DIR"
fi
cd "$REPO_DIR"

# ── 3. Python 仮想環境 + 依存パッケージ ───────────
echo ""
echo "🐍 [3/6] 仮想環境を作成し依存パッケージをインストール中..."
$PYTHON -m venv .venv
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "   インストール完了"

# ── 4. 環境変数の設定 ─────────────────────────────
echo ""
echo "🔑 [4/6] 環境変数を設定します"
echo "   （Firebase の認証情報のみ必要です。X API キー等は Firestore から自動取得されます）"
echo ""

ENV_FILE="$HOME/.xbot_env"

read -rp "FIREBASE_CREDENTIALS_BASE64 を貼り付けてください: " FB_CREDS
read -rp "DATA_UID を入力してください (例: YZnBvrP5emdmuWthTZZyS1YhTf62): " DATA_UID_VAL

cat > "$ENV_FILE" <<EOF
export FIREBASE_CREDENTIALS_BASE64="${FB_CREDS}"
export DATA_UID="${DATA_UID_VAL}"
export PYTHONPATH="${REPO_DIR}"
export TZ="Asia/Tokyo"
EOF
chmod 600 "$ENV_FILE"
echo "   環境変数を $ENV_FILE に保存しました"

# .bashrc に追記（毎回 source 不要に）
if ! grep -q "xbot_env" "$HOME/.bashrc"; then
    echo "source $ENV_FILE" >> "$HOME/.bashrc"
fi

# ── 5. Git 認証設定（コミット用）────────────────────
echo ""
echo "🔐 [5/6] Git の認証設定（キュー更新の commit/push に必要）"
echo "   GitHub の Personal Access Token (repo スコープ) を用意してください"
echo "   取得: https://github.com/settings/tokens/new?scopes=repo"
echo ""
read -rp "GitHub ユーザー名: " GH_USER
read -rp "Personal Access Token: " GH_TOKEN
read -rp "Git コミット用のメール: " GH_EMAIL

git config --global user.email "$GH_EMAIL"
git config --global user.name "$GH_USER"

# 認証情報を credential helper で保存
git config --global credential.helper store
echo "https://${GH_USER}:${GH_TOKEN}@github.com" > "$HOME/.git-credentials"
chmod 600 "$HOME/.git-credentials"

# remote を token 入り URL に変更
git remote set-url origin "https://${GH_USER}:${GH_TOKEN}@github.com/kitayama-ai/x-quote-rt-bot.git"
echo "   Git 認証設定完了"

# ── 6. ログディレクトリ作成 ──────────────────────
sudo mkdir -p "$LOG_DIR"
sudo chown "$USER:$USER" "$LOG_DIR"

# ── 7. cron ジョブ設定 ────────────────────────────
echo ""
echo "⏰ [6/6] cron ジョブを設定中..."

ACTIVATE="source $ENV_FILE && source $REPO_DIR/.venv/bin/activate && cd $REPO_DIR"
PYTHON_CMD="$REPO_DIR/.venv/bin/python -m"

# 既存の xbot cron を削除してから追加
(crontab -l 2>/dev/null | grep -v "xbot\|x-quote-rt-bot" || true) | crontab -

CRON_JOBS=$(cat <<CRON
# X Quote RT Bot — by setup_oracle_vm.sh
SHELL=/bin/bash
TZ=Asia/Tokyo

# 引用RTパイプライン (JST 08:20 / 14:00 / 20:50)
20 8 * * *  source ${ENV_FILE} && cd ${REPO_DIR} && ${REPO_DIR}/.venv/bin/python -m src.main curate-pipeline --account 1 --max-posts 2 >> ${LOG_DIR}/curate.log 2>&1
0 14 * * *  source ${ENV_FILE} && cd ${REPO_DIR} && ${REPO_DIR}/.venv/bin/python -m src.main curate-pipeline --account 1 --max-posts 2 >> ${LOG_DIR}/curate.log 2>&1
50 20 * * * source ${ENV_FILE} && cd ${REPO_DIR} && ${REPO_DIR}/.venv/bin/python -m src.main curate-pipeline --account 1 --max-posts 2 >> ${LOG_DIR}/curate.log 2>&1

# ダッシュボード操作リクエスト処理 (3分おき)
*/3 * * * * source ${ENV_FILE} && cd ${REPO_DIR} && ${REPO_DIR}/.venv/bin/python -m src.main process-operations >> ${LOG_DIR}/operations.log 2>&1 && ${REPO_DIR}/.venv/bin/python -m src.main export-dashboard --account 1 >> ${LOG_DIR}/operations.log 2>&1

# 日次ツイート収集 (JST 06:00)
0 6 * * *   source ${ENV_FILE} && cd ${REPO_DIR} && ${REPO_DIR}/.venv/bin/python -m src.main collect >> ${LOG_DIR}/collect.log 2>&1

# コードを最新に保つ (毎時0分)
0 * * * *   cd ${REPO_DIR} && git pull --rebase >> ${LOG_DIR}/gitpull.log 2>&1
CRON
)

# 既存 cron に追記
(crontab -l 2>/dev/null || true; echo "$CRON_JOBS") | crontab -
echo "   cron ジョブ設定完了"

# ── 完了 ─────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  ✅ セットアップ完了！                        ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "📋 設定済みの cron ジョブ:"
crontab -l | grep -v "^#\|^$\|^SHELL\|^TZ"
echo ""
echo "📂 ログファイル: $LOG_DIR/"
echo "   tail -f $LOG_DIR/curate.log     # パイプラインログ"
echo "   tail -f $LOG_DIR/operations.log # 操作処理ログ"
echo ""
echo "🧪 動作確認:"
echo "   source $ENV_FILE"
echo "   cd $REPO_DIR"
echo "   .venv/bin/python -m src.main curate-pipeline --account 1 --max-posts 1 --dry-run"
echo ""
echo "⚠️  GitHub Actions の scheduled ワークフローを無効化することを忘れずに！"
echo "   (deploy-dashboard.yml は残す)"
