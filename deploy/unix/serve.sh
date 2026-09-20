#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export AETHERQORE_HOME="${AETHERQORE_HOME:-$HOME/.local/share/aetherqore}"
mkdir -p "$AETHERQORE_HOME"/{data,backups,logs,config,uploads,run}
cd "$ROOT/backend"
PYTHON="${ROOT}/backend/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "Create backend/.venv and install requirements.txt first." >&2
  exit 1
fi
exec "$PYTHON" -m app serve
