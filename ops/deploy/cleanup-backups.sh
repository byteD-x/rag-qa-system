#!/usr/bin/env bash
set -euo pipefail

# Keep one rollback copy for each deployment artifact without touching runtime data.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKUP_PARENT="${BACKUP_PARENT:-$(dirname "$ROOT_DIR")}"
STAMP="$(date +%Y%m%d%H%M%S)"

case "$ROOT_DIR" in
  /opt/*) ;;
  *)
    echo "refusing to clean backups outside /opt: $ROOT_DIR" >&2
    exit 1
    ;;
esac

keep_latest() {
  local directory="$1"
  local pattern="$2"
  mapfile -t files < <(find "$directory" -maxdepth 1 -type f -name "$pattern" -printf '%T@ %p\n' | sort -nr | cut -d' ' -f2-)
  for file in "${files[@]:1}"; do
    rm -f -- "$file"
  done
}

keep_latest_dir() {
  local directory="$1"
  local pattern="$2"
  mapfile -t dirs < <(find "$directory" -maxdepth 1 -mindepth 1 -type d -name "$pattern" -printf '%T@ %p\n' | sort -nr | cut -d' ' -f2-)
  for dir in "${dirs[@]:1}"; do
    rm -rf -- "$dir"
  done
}

archive="$BACKUP_PARENT/rag-qa-system-backup-$STAMP.tgz"
tar \
  --exclude='./.env' \
  --exclude='./.env.bak.*' \
  --exclude='./ops/deploy/qdrant-data' \
  --exclude='./ops/deploy/kb-data' \
  --exclude='./apps/web/dist' \
  --exclude='./apps/web/dist.bak.*' \
  -czf "$archive" -C "$ROOT_DIR" .

keep_latest "$BACKUP_PARENT" 'rag-qa-system-backup-*.tgz'
keep_latest "$ROOT_DIR" '.env.bak.*'
keep_latest_dir "$ROOT_DIR/apps/web" 'dist.bak.*'
rm -f -- /tmp/rag-qa-system-backup-check.tgz

echo "保留源码备份: $archive"
