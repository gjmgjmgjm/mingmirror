#!/usr/bin/env bash
# MingMirror one-click local demo (macOS/Linux)
# Usage:  ./scripts/start_demo.sh
#         ./scripts/start_demo.sh --docker
#         ./scripts/start_demo.sh --smoke-only

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PORT="${PORT:-8000}"
DOCKER=0
SMOKE_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --docker) DOCKER=1 ;;
    --smoke-only) SMOKE_ONLY=1 ;;
    --port=*) PORT="${arg#*=}" ;;
  esac
done

echo "== MingMirror demo =="
echo "Root: $ROOT"

echo ""
echo "[1/3] Structure smoke (demo charts + packages)..."
python scripts/demo_smoke.py

if [[ "$SMOKE_ONLY" -eq 1 ]]; then
  echo "Smoke-only done."
  exit 0
fi

if [[ "$DOCKER" -eq 1 ]]; then
  echo ""
  echo "[2/3] Docker compose up --build..."
  docker compose up --build -d
  echo ""
  echo "[3/3] Open UI"
  echo "  Product UI : http://localhost:${PORT}/app/"
  echo "  Health     : http://localhost:${PORT}/api/v1/health"
  echo "  Demo charts: http://localhost:${PORT}/api/v1/product/demo-charts"
  echo "  Pricing code: demo-pro"
  command -v open >/dev/null && open "http://localhost:${PORT}/app/" || true
  command -v xdg-open >/dev/null && xdg-open "http://localhost:${PORT}/app/" || true
  exit 0
fi

echo ""
echo "[2/3] Frontend build (if needed)..."
if [[ ! -f web/dist/index.html ]]; then
  (cd web && { [[ -d node_modules ]] || npm install; } && npm run build)
else
  echo "  web/dist present, skip build"
fi

echo ""
echo "[3/3] Start server on port ${PORT}..."
echo "  Product UI : http://127.0.0.1:${PORT}/app/"
echo "  Demo charts: http://127.0.0.1:${PORT}/api/v1/product/demo-charts"
echo "  Pricing code: demo-pro"
export MINGMIRROR_DEMO_CODE="${MINGMIRROR_DEMO_CODE:-demo-pro}"
exec python run.py --serve --serve-host 127.0.0.1 --serve-port "$PORT"
