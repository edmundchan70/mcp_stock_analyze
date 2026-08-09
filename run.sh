#!/usr/bin/env bash
# Launch interactive Daily Run wizard (Phase 4).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT/venv/bin/python"
else
  PYTHON_BIN="$(command -v python)"
fi

echo "[preflight] Running test suite..."
if ! "$PYTHON_BIN" -m pytest -q; then
    echo "" >&2
    echo "[preflight] ABORTED: test suite failed." >&2
    echo "[preflight] The daily run was NOT started." >&2
    echo "[preflight] Fix the failing tests before running again (see output above)." >&2
    exit 1
fi

exec "$PYTHON_BIN" -m stock_analyze "$@"
