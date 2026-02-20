#!/usr/bin/env bash
set -euo pipefail

PRD_FILE="${PRD_FILE:-PRD.md}"

usage() {
  echo "Usage: $0 \"change summary\" \"files changed\" \"reason\" \"owner\""
}

if [ "$#" -ne 4 ]; then
  usage
  exit 1
fi

if [ ! -f "$PRD_FILE" ]; then
  echo "PRD file not found: $PRD_FILE"
  exit 1
fi

summary="$1"
files_changed="$2"
reason="$3"
owner="$4"
date_str="$(date +%F)"

cat >> "$PRD_FILE" <<EOT

### ${date_str}
- Change summary: ${summary}
- Files changed: ${files_changed}
- Reason: ${reason}
- Owner: ${owner}
EOT

echo "Appended change log entry to ${PRD_FILE}"
