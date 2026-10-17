#!/usr/bin/env bash
set -euo pipefail

baseline_file=${1:?baseline file is required}
target_file=${2:?target file is required}

cp -- "$baseline_file" "$target_file"
printf 'restored=%s\n' "$target_file"
