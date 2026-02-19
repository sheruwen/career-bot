#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[check] git tracked files safety"

blocked_patterns=(
  '(^|/)\.env$'
  '(^|/)\.env\.local$'
  '(^|/)\.env\.prod$'
  '(^|/)\.env\.production$'
  '(^|/)google-sheet-writer\.json$'
  '(^|/)keys/'
  'service-account.*\.json$'
  'credentials.*\.json$'
  '\.pem$'
  '\.key$'
)

tracked="$(git ls-files)"
violations=0

for pat in "${blocked_patterns[@]}"; do
  if echo "$tracked" | rg -n "$pat" >/dev/null; then
    echo "[fail] tracked sensitive file matched pattern: $pat"
    echo "$tracked" | rg -n "$pat" || true
    violations=1
  fi
done

if [[ $violations -ne 0 ]]; then
  echo "[result] FAILED"
  exit 1
fi

echo "[result] OK - no sensitive files tracked"
