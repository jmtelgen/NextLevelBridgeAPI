#!/usr/bin/env bash
# Offline with respect to AWS: pulls public build inputs but performs no deployment.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
OUTPUT="${1:-build/staging-package}"
case "$OUTPUT" in
  /*|*..*) echo "Output must be a relative project-local path without '..'." >&2; exit 2 ;;
esac
if [[ -e "$OUTPUT" ]]; then
  if [[ ! -d "$OUTPUT" ]] || [[ -n "$(find "$OUTPUT" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    echo "Output must be absent or empty; use a fresh directory for each immutable build." >&2
    exit 2
  fi
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker/BuildKit is required; run on the hosted Linux build runner. No host DDS fallback is allowed." >&2
  exit 2
fi
docker build --platform linux/amd64 \
  --file deployment/package/staging.Dockerfile --target export \
  --output "type=local,dest=$OUTPUT" .
