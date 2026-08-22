#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$REPO_ROOT/.env"
  set +a
fi

IX_ROOT="${IX_ROOT:-/srv/ix}"
GOLDEN_PATH="${GOLDEN_PATH:-$IX_ROOT/golden-path}"
HERMES_RUNTIME="${HERMES_RUNTIME:-$IX_ROOT/runtime/hermes}"
HERMES_MODELS="${HERMES_MODELS:-$IX_ROOT/models}"

echo "Preparing IX LLM runtime directories..."

owner_user="$(id -un)"
owner_group="$(id -gn)"

ensure_owned_dir() {
  local dir="$1"

  if [[ ! -d "$dir" ]]; then
    echo "Creating $dir..."
    sudo install -d -o "$owner_user" -g "$owner_group" "$dir"
  elif [[ ! -w "$dir" ]]; then
    echo "Correcting ownership of $dir..."
    sudo chown "$owner_user:$owner_group" "$dir"
  fi
}

# These paths may need privilege to establish under /srv/ix.
# Build them in order so parent directories have the intended ownership.
ensure_owned_dir "$IX_ROOT/runtime"
ensure_owned_dir "$HERMES_RUNTIME"
ensure_owned_dir "$HERMES_MODELS"
ensure_owned_dir "$HERMES_MODELS/ollama"

# Everything below lives inside directories owned by the normal IX account.
mkdir -p \
  "$HERMES_RUNTIME/memories" \
  "$HERMES_RUNTIME/.ssh" \
  "$GOLDEN_PATH/agents/leto/skills" \
  "$GOLDEN_PATH/agents/leto/job-histories"

if [[ ! -f "$GOLDEN_PATH/agents/leto/USER.md" ]]; then
  if [[ -f "$GOLDEN_PATH/USER.md" ]]; then
    cp "$GOLDEN_PATH/USER.md" "$GOLDEN_PATH/agents/leto/USER.md"
    echo "Seeded Leto USER.md from shared USER.md"
  else
    touch "$GOLDEN_PATH/agents/leto/USER.md"
    echo "Created blank Leto USER.md"
  fi
fi

chmod 700 "$HERMES_RUNTIME/.ssh"
chmod 600 "$GOLDEN_PATH/agents/leto/USER.md"

# Keep Hermes-native identity paths linked to the agent-owned Golden Path files.
# These are container-visible paths; the links intentionally appear dangling
# from the host filesystem.
ln -sfn \
  /workspace/golden-path/agents/leto/SOUL.md \
  "$HERMES_RUNTIME/SOUL.md"

ln -sfn \
  /workspace/golden-path/agents/leto/USER.md \
  "$HERMES_RUNTIME/memories/USER.md"

# Bundled Hermes skills are provided separately as an external catalog.
# Do not seed them into the agent-owned/versioned skills directory.
touch "$HERMES_RUNTIME/.no-bundled-skills"

echo "Runtime directories ready."
echo
echo "Before first launch:"
echo "  1. Copy .env.example to .env and verify HERMES_UID/HERMES_GID."
echo "  2. Ensure Leto's SSH key/config/known_hosts exist under /home/lightweight/.ssh."
echo "  3. Run the Hermes setup/auth flow interactively to configure Codex."
echo "  4. Configure dashboard authentication before exposing port 9119 through Caddy."
