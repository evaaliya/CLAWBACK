#!/usr/bin/env bash
# Deploy Clawback to a Nebius Serverless AI Endpoint.
#
# Flags below were taken from Nebius CLI docs (2026-10-29):
#   nebius ai endpoint create --help
#   https://docs.nebius.com/cli/reference/ai/endpoint/create
# Do not invent flags — re-run --help if the CLI changes.
#
# Prerequisites:
#   - nebius CLI installed and authenticated
#   - MysteryBox secrets whose payload keys are NEBIUS_API_KEY and TAVILY_API_KEY
#     ( --env-secret KEY=SECRET_SELECTOR; KEY must match the secret payload key )
#   - Public GHCR image (see .github/workflows/image.yml)
set -euo pipefail

NAME="${NAME:-clawback-demo}"
IMAGE="${IMAGE:-ghcr.io/evaaliya/clawback:latest}"
PLATFORM="${PLATFORM:-cpu-d3}"
PRESET="${PRESET:-2vcpu-8gb}"
DISK_SIZE="${DISK_SIZE:-20Gi}"
CONTAINER_PORT="${CONTAINER_PORT:-8000}"
JOB_TOKEN="${JOB_TOKEN:-}"
NEBIUS_SECRET="${NEBIUS_SECRET:-NEBIUS_API_KEY}"
TAVILY_SECRET="${TAVILY_SECRET:-TAVILY_API_KEY}"
PARENT_ID="${PARENT_ID:-}"

if ! command -v nebius >/dev/null 2>&1; then
  echo "nebius CLI not found. Install it, then re-run:" >&2
  echo "  nebius ai endpoint create --help" >&2
  echo "  nebius ai create --help" >&2
  exit 1
fi

echo "Using verified flags from: nebius ai endpoint create --help"
echo "  --image --container-port --env --env-secret --public --auth --name --platform --preset --disk-size"
echo "Auth: --auth none (opens in a normal browser without a token)"
echo "Platform: $PLATFORM / $PRESET (CPU; models run on Token Factory)"

ARGS=(
  ai endpoint create
  --name "$NAME"
  --image "$IMAGE"
  --container-port "$CONTAINER_PORT"
  --platform "$PLATFORM"
  --preset "$PRESET"
  --disk-size "$DISK_SIZE"
  --public
  --auth none
  --env "RECORDED_MODE=false"
  --env "DEMO_RESET=enabled"
  --env "DEMO_TODAY=2026-10-27"
  --env "POLICY_JURISDICTION=US"
  --env "DATABASE_PATH=/data/clawback.db"
  --env "LIVE_LLM_DAILY_LIMIT=300"
  --env-secret "NEBIUS_API_KEY=${NEBIUS_SECRET}"
  --env-secret "TAVILY_API_KEY=${TAVILY_SECRET}"
)

if [[ -n "$JOB_TOKEN" ]]; then
  ARGS+=(--env "JOB_TOKEN=${JOB_TOKEN}")
fi
if [[ -n "$PARENT_ID" ]]; then
  ARGS+=(--parent-id "$PARENT_ID")
fi

echo "Creating endpoint…"
# --format json returns the Operation; resource_id is the endpoint id.
OP_JSON=$(nebius "${ARGS[@]}" --format json)
ENDPOINT_ID=$(printf '%s' "$OP_JSON" | python3 -c "
import json,sys
data=json.load(sys.stdin)
print(data.get('resource_id') or data.get('id') or '')
")

if [[ -z "$ENDPOINT_ID" ]]; then
  echo "Could not parse endpoint id from create response:" >&2
  echo "$OP_JSON" >&2
  exit 1
fi

echo "Endpoint id: $ENDPOINT_ID"
echo "Waiting for ready status (poll get)…"
for _ in $(seq 1 60); do
  GET_JSON=$(nebius ai endpoint get "$ENDPOINT_ID" --format json)
  READY=$(printf '%s' "$GET_JSON" | python3 -c "
import json,sys
d=json.load(sys.stdin)
status=d.get('status') or {}
# Prefer managed HTTPS URLs; fall back to public_ip as older docs describe.
eps=status.get('public_endpoints') or []
https=[e for e in eps if isinstance(e,str) and e.startswith('https://')]
ip=None
instances=status.get('instances') or []
if instances and isinstance(instances[0], dict):
    ip=instances[0].get('public_ip')
if not ip:
    ip=status.get('public_ip')
url=https[0] if https else (f'http://{ip}:8000' if ip else '')
print(url)
" )
  if [[ -n "$READY" ]]; then
    echo "Public demo URL: $READY"
    echo "$ENDPOINT_ID" > .nebius-endpoint-id
    echo "Saved id to .nebius-endpoint-id"
    exit 0
  fi
  sleep 5
done

echo "Timed out waiting for a public URL. Inspect with:" >&2
echo "  nebius ai endpoint get $ENDPOINT_ID --format json" >&2
exit 1
