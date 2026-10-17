#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SOURCE_FILE="$SCRIPT_DIR/MODIFIED_FILE"
TARGET_FILE="${1:-$SCRIPT_DIR/ROLLBACK_COPY}"

cp -- "$SOURCE_FILE" "$TARGET_FILE"
cmp -- "$SOURCE_FILE" "$TARGET_FILE"
printf 'ROLLBACK_RESULT=restored:%s\n' "$TARGET_FILE"
