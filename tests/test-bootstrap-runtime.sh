#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/repo/scripts"
cp "$repo_root/scripts/bootstrap-runtime.sh" "$tmp/repo/scripts/"

ix_root="$tmp/ix"
golden_path="$ix_root/golden-path"
hermes_runtime="$ix_root/runtime/hermes"
hermes_models="$ix_root/models"

mkdir -p \
  "$ix_root/runtime" \
  "$hermes_runtime" \
  "$hermes_models/ollama" \
  "$golden_path"

cat >"$tmp/repo/.env" <<EOF
IX_ROOT=$ix_root
GOLDEN_PATH=$golden_path
HERMES_RUNTIME=$hermes_runtime
HERMES_MODELS=$hermes_models
EOF

(
  unset IX_ROOT GOLDEN_PATH HERMES_RUNTIME HERMES_MODELS
  cd "$tmp/repo"
  ./scripts/bootstrap-runtime.sh >/dev/null
)

test -d "$hermes_runtime/memories"
test -d "$golden_path/agents/leto/skills"
test -L "$hermes_runtime/SOUL.md"
test -f "$hermes_runtime/.no-bundled-skills"

printf 'bootstrap-runtime loads repository .env: PASS\n'
