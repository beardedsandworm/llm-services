#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
MACHINE_ID="${MACHINE_ID:-$(hostname -s)}"

# shellcheck source=/dev/null
source "${SCRIPT_DIR}/lib/notify-discord.sh"

for cmd in docker jq; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "[ERROR] Required command not found: ${cmd}"
    exit 1
  fi
done

if ! docker buildx version >/dev/null 2>&1; then
  echo "[ERROR] docker buildx is required"
  exit 1
fi

if [[ ! -x "${REPO_ROOT}/dc" ]]; then
  echo "[ERROR] Missing executable Compose wrapper: ${REPO_ROOT}/dc"
  exit 1
fi

cd "${REPO_ROOT}"

COMPOSE=(
  "${REPO_ROOT}/dc"
)

send_check_error() {
  local title="$1"
  local message="$2"

  if declare -F send_discord_error >/dev/null 2>&1; then
    send_discord_error \
      "${title}" \
      "${message}" \
      "docker-image-check"
  else
    send_discord_info \
      "${title}" \
      "${message}" \
      "docker-image-check"
  fi
}

if ! CONFIG_JSON="$("${COMPOSE[@]}" config --format json)"; then
  MESSAGE="Unable to render Docker Compose configuration for ${MACHINE_ID}"

  echo "[ERROR] ${MESSAGE}"
  send_check_error "Image Check Failed" "${MESSAGE}"
  exit 1
fi

if ! SERVICE_ROWS="$(
  jq -r '
    .services
    | to_entries[]
    | [
        .key,
        (if .value.build != null then "true" else "false" end),
        (.value.image // "")
      ]
    | @tsv
  ' <<<"${CONFIG_JSON}"
)"; then
  MESSAGE="Unable to parse Docker Compose services for ${MACHINE_ID}"

  echo "[ERROR] ${MESSAGE}"
  send_check_error "Image Check Failed" "${MESSAGE}"
  exit 1
fi

UPDATED_SERVICES=()
CHECK_ERRORS=()
PINNED_SERVICES=()
LOCAL_BUILD_SERVICES=()

TOTAL_COUNT=0
CHECKED_COUNT=0

while IFS=$'\t' read -r SERVICE BUILD IMAGE; do
  [[ -n "${SERVICE}" ]] || continue

  ((TOTAL_COUNT += 1))

  # Services with a Compose build section are locally built.
  # Examples: custom Caddy images and Hermes.
  if [[ "${BUILD}" == "true" ]]; then
    LOCAL_BUILD_SERVICES+=("${SERVICE}")
    continue
  fi

  # Ignore services with neither a build nor an image.
  [[ -n "${IMAGE}" ]] || continue

  # Immutable digest-pinned references do not need remote tag checks.
  if [[ "${IMAGE}" == *@sha256:* ]]; then
    PINNED_SERVICES+=("${SERVICE}")
    continue
  fi

  # Find the container actually deployed for this Compose service.
  CONTAINER_ID="$(
    "${COMPOSE[@]}" ps \
      --all \
      --quiet \
      "${SERVICE}" \
      2>/dev/null \
      | head -n 1
  )"

  if [[ -z "${CONTAINER_ID}" ]]; then
    CHECK_ERRORS+=("${SERVICE}: no deployed container found")
    continue
  fi

  RUNNING_IMAGE_ID="$(
    docker inspect \
      --format '{{.Image}}' \
      "${CONTAINER_ID}" \
      2>/dev/null || true
  )"

  if [[ -z "${RUNNING_IMAGE_ID}" ]]; then
    CHECK_ERRORS+=("${SERVICE}: unable to determine deployed image")
    continue
  fi

  # Image currently associated with the configured tag in the local cache.
  LOCAL_TAG_IMAGE_ID="$(
    docker image inspect \
      --format '{{.Id}}' \
      "${IMAGE}" \
      2>/dev/null || true
  )"

  if [[ -z "${LOCAL_TAG_IMAGE_ID}" ]]; then
    CHECK_ERRORS+=("${SERVICE}: configured image is not present locally")
    continue
  fi

  # If a newer image has already been pulled but the container has not been
  # recreated, an update is already pending and no registry lookup is needed.
  if [[ "${RUNNING_IMAGE_ID}" != "${LOCAL_TAG_IMAGE_ID}" ]]; then
    ((CHECKED_COUNT += 1))
    UPDATED_SERVICES+=("${SERVICE}")
    continue
  fi

  # Ask Buildx for the immutable digest of the configured remote tag.
  if ! REMOTE_OUTPUT="$(
    docker buildx imagetools inspect \
      "${IMAGE}" \
      --format '{{json .Manifest.Digest}}' \
      2>&1
  )"; then
    ERROR_DETAIL="$(
      printf '%s\n' "${REMOTE_OUTPUT}" \
        | tail -n 1 \
        | tr -s '[:space:]' ' '
    )"

    CHECK_ERRORS+=("${SERVICE}: registry lookup failed: ${ERROR_DETAIL}")
    continue
  fi

  if ! REMOTE_DIGEST="$(
    jq -r '
      if type == "string" then .
      else empty
      end
    ' <<<"${REMOTE_OUTPUT}" 2>/dev/null
  )"; then
    CHECK_ERRORS+=("${SERVICE}: invalid registry response")
    continue
  fi

  if [[ -z "${REMOTE_DIGEST}" || "${REMOTE_DIGEST}" == "null" ]]; then
    RESPONSE="$(
      printf '%s' "${REMOTE_OUTPUT}" \
        | head -c 160 \
        | tr '\n' ' '
    )"

    CHECK_ERRORS+=(
      "${SERVICE}: registry returned no digest (${RESPONSE})"
    )
    continue
  fi

  LOCAL_REPO_DIGESTS="$(
    docker image inspect \
      --format '{{json .RepoDigests}}' \
      "${IMAGE}" \
      2>/dev/null \
      | jq -r '.[]? | split("@")[-1]'
  )"

  if [[ -z "${LOCAL_REPO_DIGESTS}" ]]; then
    CHECK_ERRORS+=("${SERVICE}: local image has no repository digest")
    continue
  fi

  ((CHECKED_COUNT += 1))

  if ! grep -Fxq "${REMOTE_DIGEST}" <<<"${LOCAL_REPO_DIGESTS}"; then
    UPDATED_SERVICES+=("${SERVICE}")
  fi

done <<<"${SERVICE_ROWS}"

UPDATE_COUNT="${#UPDATED_SERVICES[@]}"
ERROR_COUNT="${#CHECK_ERRORS[@]}"
PINNED_COUNT="${#PINNED_SERVICES[@]}"
LOCAL_BUILD_COUNT="${#LOCAL_BUILD_SERVICES[@]}"

LOCAL_BUILD_SECTION=""

if (( LOCAL_BUILD_COUNT > 0 )); then
  LOCAL_BUILD_LIST="$(
    printf '• %s\n' "${LOCAL_BUILD_SERVICES[@]}" \
      | head -n 15
  )"

  if (( LOCAL_BUILD_COUNT > 15 )); then
    LOCAL_BUILD_LIST+=$'\n'"• …and $((LOCAL_BUILD_COUNT - 15)) more"
  fi

  LOCAL_BUILD_SECTION=$(cat <<EOF

Locally built images skipped: ${LOCAL_BUILD_COUNT}

${LOCAL_BUILD_LIST}
EOF
)
fi

if (( ERROR_COUNT > 0 )); then
  ERROR_LIST="$(
    printf '• %s\n' "${CHECK_ERRORS[@]}" \
      | head -n 15
  )"

  if (( ERROR_COUNT > 15 )); then
    ERROR_LIST+=$'\n'"• …and $((ERROR_COUNT - 15)) more"
  fi

  MESSAGE=$(cat <<EOF
Image update check could not complete cleanly on ${MACHINE_ID}.

Image services found: ${TOTAL_COUNT}
Images checked successfully: ${CHECKED_COUNT}
Check errors: ${ERROR_COUNT}
Pinned images skipped: ${PINNED_COUNT}
${LOCAL_BUILD_SECTION}

${ERROR_LIST}
EOF
)

  printf '%s\n' "${MESSAGE}"

  send_check_error \
    "Image Check Failed" \
    "${MESSAGE}"

  exit 1
fi

if (( UPDATE_COUNT > 0 )); then
  SERVICE_LIST="$(
    printf '• %s\n' "${UPDATED_SERVICES[@]}" \
      | head -n 15
  )"

  if (( UPDATE_COUNT > 15 )); then
    SERVICE_LIST+=$'\n'"• …and $((UPDATE_COUNT - 15)) more"
  fi

  MESSAGE=$(cat <<EOF
Image updates available on ${MACHINE_ID}

Images checked: ${CHECKED_COUNT}
Running containers with image updates: ${UPDATE_COUNT}
Pinned images skipped: ${PINNED_COUNT}
${LOCAL_BUILD_SECTION}

${SERVICE_LIST}
EOF
)

  printf '%s\n' "${MESSAGE}"

  send_discord_info \
    "Image Updates Available" \
    "${MESSAGE}" \
    "docker-image-check"

  exit 0
fi

MESSAGE=$(cat <<EOF
All ${CHECKED_COUNT} checked container images are up to date on ${MACHINE_ID}

Pinned images skipped: ${PINNED_COUNT}
${LOCAL_BUILD_SECTION}
EOF
)

printf '%s\n' "${MESSAGE}"

exit 0
