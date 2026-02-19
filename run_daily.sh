#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

python3 job_tool.py --rules rules.json --output-dir outputs
