#!/bin/bash
# =============================================================================
# Oracle Cloud Free Tier VM セットアップスクリプト
# Ubuntu 22.04 / 24.04 (ARM Ampere / AMD) 対応
#
# 使い方:
#   SSH で VM に接続後、リポジトリをクローンして実行:
#
#   git clone https://github.com/kitayama-ai/x-quote-rt-bot.git
#   cd x-quote-rt-bot
#   bash scripts/setup_oracle_vm.sh
#
# 実行すると対話形式で以下を入力:
#   - FIREBASE_CREDENTIALS_BASE64 (GitHub Secrets の値をコピペ)
#   - DATA_UID (例: YZnBvrP5emdmuWthTZZyS1YhTf62)
#   - GitHub Personal Access Token (repo スコープ, push 用)
#   - GitHub ユーザー名 / メール
#
# 起動するサービス (systemd timer):
#   xbot-pipeline.timer      → 毎日 JST 08:20 / 14:00 / 20:50 に投稿パイプライン
#   xbot-operations.timer    → 3分おきに操作リクエスト処理
#   xbot-collect.timer       → 毎日 JST 06:00 にバズツイート収集
#   xbot-metrics.timer       → 毎日 JST 23:00 にメトリクス収集
#   xbot-gitpull.timer       → 毎時コードを最新化
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_USER="${USER}"
VENV="${REPO_DIR}/.venv"
PYTHON="${VENV}/bin/python"
LOG_DIR="/var/log/xbot"
SYSTEMD_DIR="/etc/systemd/system"
ENV_FILE="/etc/xbot/env"

echo "╔══════════════════════════════════════════════╗"
echo "║  X Quote RT Bot — Oracle VM セットアップ     ║"
echo "║  $(date '+%Y-%m-%d %H:%M:%S JST')                  ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "📂 リポジトリ: ${REPO_DIR}"

# ── 1. システムパッケージ ─────────────────────────
echo ""
echo "📦 [1/7] システムパッケージをインストール..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv git curl logrotate
echo "   Python: $(python3 --version)"

# ── 2. 仮想環境 + 依存パッケージ ─────────────────
echo ""
echo "🐍 [2/7] Python 仮想環境を構築..."
python3 -m venv "${VENV}"
"${VENV}/bin/pip" install --quiet --upgrade pip
"${VENV}/bin/pip" install --quiet -r "${REPO_DIR}/requirements.txt"
echo "   完了"

# ── 3. 環境変数ファイル ───────────────────────────
echo ""
echo "🔑 [3/7] 環境変数を設定します"
echo "   (X API キー等は Firestore から自動取得されます)"
echo ""

sudo mkdir -p "$(dirname ${ENV_FILE})"

read -rp "FIREBASE_CREDENTIALS_BASE64 を貼り付けてください: " FB_CREDS
read -rp "DATA_UID を入力してください (例: YZnBvrP5emdmuWthTZZyS1YhTf62): " DATA_UID_VAL

sudo tee "${ENV_FILE}" > /dev/null <<ENVEOF
FIREBASE_CREDENTIALS_BASE64=${FB_CREDS}
DATA_UID=${DATA_UID_VAL}
TZ=Asia/Tokyo
PYTHONPATH=${REPO_DIR}
ENVEOF
sudo chmod 600 "${ENV_FILE}"
sudo chown root:root "${ENV_FILE}"
echo "   環境変数を ${ENV_FILE} に保存"

# ── 4. Git 認証設定 ───────────────────────────────
echo ""
echo "🔐 [4/7] Git 認証設定（キュー更新の push 用）"
echo "   https://github.com/settings/tokens/new?scopes=repo でトークン取得"
echo ""
read -rp "GitHub ユーザー名: " GH_USER
read -rp "Personal Access Token: " GH_TOKEN
read -rp "Git コミット用メール: " GH_EMAIL

git -C "${REPO_DIR}" config user.email "${GH_EMAIL}"
git -C "${REPO_DIR}" config user.name "${GH_USER}"
git -C "${REPO_DIR}" remote set-url origin \
    "https://${GH_USER}:${GH_TOKEN}@github.com/kitayama-ai/x-quote-rt-bot.git"
echo "   完了"

# ── 5. ログディレクトリ + ローテーション ─────────
echo ""
echo "📋 [5/7] ログ設定..."
sudo mkdir -p "${LOG_DIR}"
sudo chown "${SERVICE_USER}:${SERVICE_USER}" "${LOG_DIR}"

sudo tee /etc/logrotate.d/xbot > /dev/null <<'LOGEOF'
/var/log/xbot/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 644 ubuntu ubuntu
}
LOGEOF
echo "   ログローテーション: 14日保持"

# ── 6. systemd サービス + タイマー定義 ──────────
echo ""
echo "⚙️  [6/7] systemd サービス/タイマーを設定..."

# ── 共通ヘルパー関数 ──
create_service() {
    local name="$1"
    local description="$2"
    local exec_cmd="$3"

    sudo tee "${SYSTEMD_DIR}/${name}.service" > /dev/null <<EOF
[Unit]
Description=XBot ${description}
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=${SERVICE_USER}
WorkingDirectory=${REPO_DIR}
EnvironmentFile=${ENV_FILE}
ExecStartPre=/usr/bin/git -C ${REPO_DIR} pull --rebase origin main
ExecStart=${PYTHON} -m ${exec_cmd}
StandardOutput=append:${LOG_DIR}/${name}.log
StandardError=append:${LOG_DIR}/${name}.log
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF
}

create_timer() {
    local name="$1"
    local description="$2"
    local on_calendar="$3"       # systemd OnCalendar 形式

    sudo tee "${SYSTEMD_DIR}/${name}.timer" > /dev/null <<EOF
[Unit]
Description=XBot ${description} Timer
Requires=${name}.service

[Timer]
OnCalendar=${on_calendar}
Persistent=true
AccuracySec=30s

[Install]
WantedBy=timers.target
EOF
}

# ─ パイプライン (JST 08:20 / 14:00 / 20:50) ─
create_service "xbot-pipeline" \
    "引用RTパイプライン" \
    "src.main curate-pipeline --account 1 --max-posts 2"

# JST = UTC+9: 08:20JST=23:20UTC, 14:00JST=05:00UTC, 20:50JST=11:50UTC
sudo tee "${SYSTEMD_DIR}/xbot-pipeline.timer" > /dev/null <<EOF
[Unit]
Description=XBot 引用RTパイプライン Timer (JST 08:20 / 14:00 / 20:50)
Requires=xbot-pipeline.service

[Timer]
OnCalendar=*-*-* 23:20:00
OnCalendar=*-*-* 05:00:00
OnCalendar=*-*-* 11:50:00
Persistent=true
AccuracySec=30s

[Install]
WantedBy=timers.target
EOF

# ─ 操作リクエスト処理 (3分おき) ─
# process-operations の後に export-dashboard も実行するラッパースクリプト
sudo tee "${REPO_DIR}/scripts/run_operations.sh" > /dev/null <<OPSEOF
#!/bin/bash
set -euo pipefail
cd "${REPO_DIR}"
"${PYTHON}" -m src.main process-operations
"${PYTHON}" -m src.main export-dashboard --account 1 || true
# 変更をコミット & プッシュ
git add data/queue/ public/dashboard-data.json config/ 2>/dev/null || true
git diff --staged --quiet || git commit -m "chore: vm operations \$(date +'%Y-%m-%d %H:%M')"
git pull --rebase origin main || true
git push origin main || true
OPSEOF
chmod +x "${REPO_DIR}/scripts/run_operations.sh"

sudo tee "${SYSTEMD_DIR}/xbot-operations.service" > /dev/null <<EOF
[Unit]
Description=XBot 操作リクエスト処理
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=${SERVICE_USER}
WorkingDirectory=${REPO_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=/bin/bash ${REPO_DIR}/scripts/run_operations.sh
StandardOutput=append:${LOG_DIR}/xbot-operations.log
StandardError=append:${LOG_DIR}/xbot-operations.log
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
EOF

create_timer "xbot-operations" "操作リクエスト処理" "*:0/3"

# ─ 日次収集 (JST 06:00 = UTC 21:00) ─
create_service "xbot-collect" \
    "バズツイート収集" \
    "src.main collect"
create_timer "xbot-collect" "バズツイート収集" "*-*-* 21:00:00"

# ─ パイプライン後のキューコミット用ラッパー ─
sudo tee "${REPO_DIR}/scripts/run_pipeline.sh" > /dev/null <<PIPEEOF
#!/bin/bash
set -euo pipefail
cd "${REPO_DIR}"
git pull --rebase origin main || true
"${PYTHON}" -m src.main curate-pipeline --account 1 --max-posts 2
git add data/queue/ 2>/dev/null || true
git diff --staged --quiet || git commit -m "chore: vm pipeline \$(date +'%Y-%m-%d %H:%M')"
git pull --rebase origin main || true
git push origin main || true
PIPEEOF
chmod +x "${REPO_DIR}/scripts/run_pipeline.sh"

# pipeline.service を run_pipeline.sh 使用版に上書き
sudo tee "${SYSTEMD_DIR}/xbot-pipeline.service" > /dev/null <<EOF
[Unit]
Description=XBot 引用RTパイプライン（収集→生成→投稿）
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=${SERVICE_USER}
WorkingDirectory=${REPO_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=/bin/bash ${REPO_DIR}/scripts/run_pipeline.sh
StandardOutput=append:${LOG_DIR}/xbot-pipeline.log
StandardError=append:${LOG_DIR}/xbot-pipeline.log
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

# ─ 日次メトリクス (JST 23:00 = UTC 14:00) ─
create_service "xbot-metrics" \
    "メトリクス収集" \
    "src.main metrics --account 1"
create_timer "xbot-metrics" "メトリクス収集" "*-*-* 14:00:00"

# ─ 週次PDCA (月曜 JST 09:00 = UTC 00:00) ─
create_service "xbot-weekly-pdca" \
    "週次PDCAレポート" \
    "src.main weekly-pdca --account 1"

sudo tee "${SYSTEMD_DIR}/xbot-weekly-pdca.timer" > /dev/null <<EOF
[Unit]
Description=XBot 週次PDCAレポート Timer (毎週月曜 JST 09:00)
Requires=xbot-weekly-pdca.service

[Timer]
OnCalendar=Mon *-*-* 00:00:00
Persistent=true
AccuracySec=60s

[Install]
WantedBy=timers.target
EOF

# ── 7. systemd 有効化 & 起動 ─────────────────────
echo ""
echo "🚀 [7/7] systemd タイマーを有効化..."
sudo systemctl daemon-reload

TIMERS=(xbot-pipeline xbot-operations xbot-collect xbot-metrics xbot-weekly-pdca)
for t in "${TIMERS[@]}"; do
    sudo systemctl enable --now "${t}.timer" 2>/dev/null && \
        echo "   ✅ ${t}.timer" || \
        echo "   ⚠️  ${t}.timer (スキップ)"
done

# ── 完了 ─────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  ✅ セットアップ完了！                        ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "📋 起動中のタイマー:"
systemctl list-timers 'xbot-*' --no-pager 2>/dev/null || true
echo ""
echo "🔍 ログ確認コマンド:"
echo "   sudo journalctl -u xbot-pipeline -f    # パイプラインログ（リアルタイム）"
echo "   sudo journalctl -u xbot-operations -f  # 操作処理ログ"
echo "   tail -f ${LOG_DIR}/xbot-pipeline.log   # ファイルログ"
echo ""
echo "🧪 手動実行テスト:"
echo "   sudo systemctl start xbot-pipeline.service"
echo "   sudo journalctl -u xbot-pipeline --no-pager"
echo ""
echo "⏰ 次回実行予定:"
echo "   systemctl list-timers 'xbot-*'"
