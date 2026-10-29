#!/usr/bin/env bash
# Run the deadline scan against the public endpoint via a Nebius Serverless Job.
#
# Flags from: nebius ai job create --help
#   https://docs.nebius.com/cli/reference/ai/job/create
# Jobs are on-demand (one-off). Do not claim scheduling unless Nebius docs add it.
set -euo pipefail

NAME="${NAME:-clawback-scan}"
IMAGE="${IMAGE:-ghcr.io/evaaliya/clawback:latest}"
PLATFORM="${PLATFORM:-cpu-d3}"
PRESET="${PRESET:-2vcpu-8gb}"
DISK_SIZE="${DISK_SIZE:-20Gi}"
TIMEOUT="${TIMEOUT:-10m}"
SCAN_TARGET_URL="${SCAN_TARGET_URL:?Set SCAN_TARGET_URL to the public demo base URL}"
JOB_TOKEN="${JOB_TOKEN:-}"
PARENT_ID="${PARENT_ID:-}"

if ! command -v nebius >/dev/null 2>&1; then
  echo "nebius CLI not found. Install it, then run: nebius ai job create --help" >&2
  exit 1
fi

ARGS=(
  ai job create
  --name "$NAME"
  --image "$IMAGE"
  --container-command "python"
  --args "jobs/scan.py"
  --platform "$PLATFORM"
  --preset "$PRESET"
  --disk-size "$DISK_SIZE"
  --timeout "$TIMEOUT"
  --env "SCAN_TARGET_URL=${SCAN_TARGET_URL}"
)

if [[ -n "$JOB_TOKEN" ]]; then
  ARGS+=(--env "JOB_TOKEN=${JOB_TOKEN}")
fi
if [[ -n "$PARENT_ID" ]]; then
  ARGS+=(--parent-id "$PARENT_ID")
fi

echo "Creating on-demand scan job (no schedule)…"
nebius "${ARGS[@]}" --format json
echo "Job submitted. View logs with: nebius ai job get <id> --format json"
