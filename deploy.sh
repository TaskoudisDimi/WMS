#!/usr/bin/env bash
# Deploy WMS to the server: checks → push → pull, install, migrate, build, restart.
#
#   ./deploy.sh                 full deploy
#   ./deploy.sh --skip-checks   skip local tests/build (when you just ran them)
#
# Settings (env vars or a git-ignored .deploy.env next to this script):
#   DEPLOY_HOST   ssh target              (default root@188.245.64.189)
#   DEPLOY_DIR    repo path on the server (default /var/www/wms)
set -euo pipefail

ROOT=$(cd "$(dirname "$0")" && pwd)
[[ -f "$ROOT/.deploy.env" ]] && source "$ROOT/.deploy.env"
DEPLOY_HOST=${DEPLOY_HOST:-root@188.245.64.189}
DEPLOY_DIR=${DEPLOY_DIR:-/var/www/wms}
SKIP_CHECKS=false
[[ "${1:-}" == "--skip-checks" ]] && SKIP_CHECKS=true

bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

cd "$ROOT"
bold "1/4  Checking the working tree"
[[ -z "$(git status --porcelain)" ]] || fail "Uncommitted changes. Commit or stash them first."
branch=$(git rev-parse --abbrev-ref HEAD)
[[ "$branch" == "master" ]] || fail "On branch '$branch' — deploy from master."
git fetch -q origin
[[ -z "$(git log HEAD..origin/master --oneline)" ]] || fail "origin/master has commits you don't have. git pull first."

if ! $SKIP_CHECKS; then
  bold "2/4  Running tests and a production build locally"
  PY=wms/backend/venv/bin/python
  [[ -x $PY ]] || PY=wms/backend/ai-bus-assistant/bin/python
  [[ -x $PY ]] || fail "No backend virtualenv. Run ./run-local.sh once to create it."
  (cd wms/backend && "$ROOT/$PY" -m pytest -q) || fail "Backend tests failed"
  (cd wms/frontend/ui && npx vue-tsc --build && npm run build-only >/dev/null) || fail "Frontend build failed"
else
  bold "2/4  Skipping local checks"
fi

bold "3/4  Pushing to GitHub"
git push -q origin master
echo "pushed $(git rev-parse --short HEAD)"

bold "4/4  Updating $DEPLOY_HOST:$DEPLOY_DIR"
ssh "$DEPLOY_HOST" DEPLOY_DIR="$DEPLOY_DIR" 'bash -s' < <(sed -n '/^# ── remote ──/,$p' "$0")
bold "Deployed ✓  https://wms.task-code.com"
exit 0

# ── remote ── everything below runs on the server (piped over ssh) ────────────
set -euo pipefail
cd "$DEPLOY_DIR"
step() { printf '  → %s\n' "$*"; }

# New code may need new columns: refuse to deploy if migrations can't run,
# before touching anything, so the running version keeps working.
if ! grep -qE '^DATABASE_URL=.+' wms/backend/.env 2>/dev/null; then
  echo "  ✗ DATABASE_URL missing in wms/backend/.env (needed for migrations). Nothing was changed." >&2; exit 1
fi
command -v psql >/dev/null || { echo "  ✗ psql not installed (apt install postgresql-client). Nothing was changed." >&2; exit 1; }
changed() { ! git -C "$DEPLOY_DIR" diff --quiet "$OLD" HEAD -- "$@"; }

OLD=$(git rev-parse HEAD)
git pull -q --ff-only
NEW=$(git rev-parse HEAD)
step "code $(git rev-parse --short "$OLD") → $(git rev-parse --short "$NEW")"

BACKEND="$DEPLOY_DIR/wms/backend"
FRONTEND="$DEPLOY_DIR/wms/frontend/ui"

cd "$BACKEND"
if [[ ! -x venv/bin/python ]]; then
  step "creating virtualenv"
  python3.12 -m venv venv 2>/dev/null || python3 -m venv venv
  venv/bin/pip install -q -r requirements.txt
elif changed wms/backend/requirements.txt; then
  step "installing Python packages"
  venv/bin/pip install -q -r requirements.txt
fi

step "database migrations"
scripts/migrate.sh | sed 's/^/     /'

cd "$FRONTEND"
if [[ ! -d node_modules ]] || changed wms/frontend/ui/package-lock.json; then
  step "installing npm packages"
  npm ci --silent
fi
step "building frontend"
npm run build-only --silent >/dev/null

step "systemd units"
for unit in "$DEPLOY_DIR"/wms/deploy/systemd/*; do
  sed "s#@BACKEND_DIR@#$BACKEND#g" "$unit" > "${SYSTEMD_DIR:-/etc/systemd/system}/$(basename "$unit")"
done
chmod +x "$BACKEND"/scripts/*.sh
systemctl daemon-reload
systemctl enable -q --now wms-alerts.timer wms-invoicing.timer
systemctl enable -q --now wms-backup.timer

step "restarting backend"
systemctl restart wms-backend
for i in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8001/api/health >/dev/null 2>&1; then
    echo "  ✓ healthy"
    exit 0
  fi
  sleep 1
done
echo "  ✗ backend did not become healthy — last log lines:" >&2
journalctl -u wms-backend -n 30 --no-pager >&2
exit 1
