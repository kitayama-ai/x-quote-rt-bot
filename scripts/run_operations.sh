#!/bin/bash
# 操作リクエスト処理 + ダッシュボードエクスポート + git push
# systemd xbot-operations.service から呼び出される
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${REPO_DIR}/.venv/bin/python"

cd "${REPO_DIR}"

"${PYTHON}" -m src.main process-operations
"${PYTHON}" -m src.main export-dashboard --account 1 || true

# 変更をコミット & プッシュ
git add data/queue/ public/dashboard-data.json config/ 2>/dev/null || true
if ! git diff --staged --quiet; then
    git commit -m "chore: vm operations $(date +'%Y-%m-%d %H:%M')"
    git pull --rebase origin main || true
    git push origin main || true
fi
