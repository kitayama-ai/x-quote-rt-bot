#!/bin/bash
# 引用RTパイプライン実行 + キュー変更を git push
# systemd xbot-pipeline.service から呼び出される
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${REPO_DIR}/.venv/bin/python"

cd "${REPO_DIR}"
git pull --rebase origin main || true

"${PYTHON}" -m src.main curate-pipeline --account 1 --max-posts 2

# キューの変更をコミット & プッシュ
git add data/queue/ 2>/dev/null || true
if ! git diff --staged --quiet; then
    git commit -m "chore: vm pipeline $(date +'%Y-%m-%d %H:%M')"
    git pull --rebase origin main || true
    git push origin main || true
fi
