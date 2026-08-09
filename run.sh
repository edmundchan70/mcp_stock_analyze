#!/usr/bin/env bash
# Launch interactive Daily Run wizard (Phase 4).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/venv/bin/python" ]]; then
  exec "$ROOT/venv/bin/python" -m stock_analyze "$@"
else
  exec python -m stock_analyze "$@"
fi
