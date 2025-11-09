#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"
CONFIG_PATH="$ROOT_DIR/wrangler.toml"
TEMPLATE_PATH="$ROOT_DIR/wrangler.toml-example"
STATE_NAMESPACE_NAME="notion-caldav-sync-STATE"  # Change if you prefer a different namespace title.

cd "$ROOT_DIR"

if [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
  echo "CLOUDFLARE_ACCOUNT_ID is required for Wrangler operations." >&2
  exit 1
fi

if [ -z "${CLOUDFLARE_API_TOKEN:-}" ]; then
  echo "CLOUDFLARE_API_TOKEN is required for Wrangler operations." >&2
  exit 1
fi

# Helper to discover namespace ID via Wrangler CLI
discover_namespace_id() {
  if list_json=$(uv run -- pywrangler kv namespace list 2>/dev/null); then
    LIST_JSON="$list_json" python3 - "$STATE_NAMESPACE_NAME" <<'PY'
import json
import os
import sys

title = sys.argv[1]
raw = os.environ.get("LIST_JSON", "")
if not raw:
    sys.exit(0)

buffer = raw.strip()
if not buffer:
    sys.exit(0)

def extract_json(blob):
    """Best-effort extraction of the JSON payload from Wrangler's noisy output."""
    # Fast path: try the entire blob first.
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        pass

    # Remove common log noise (INFO lines, banners, unicode art, etc.).
    cleaned_lines = []
    for line in blob.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(stripped.startswith(prefix) for prefix in ("INFO ", "⛅️", "🌀", "✘", "───────────────────", "Resource location:")):
            continue
        cleaned_lines.append(line)
    cleaned_blob = "\n".join(cleaned_lines).strip()
    if not cleaned_blob:
        raise ValueError

    # Try parsing the cleaned blob.
    try:
        return json.loads(cleaned_blob)
    except json.JSONDecodeError:
        pass

    # Fall back to slicing between the first opening bracket/brace and the matching closing char.
    for opener, closer in (("[", "]"), ("{", "}")):
        start = cleaned_blob.find(opener)
        end = cleaned_blob.rfind(closer)
        if start == -1 or end == -1 or end <= start:
            continue
        segment = cleaned_blob[start : end + 1]
        try:
            return json.loads(segment)
        except json.JSONDecodeError:
            continue
    raise ValueError

try:
    payload = extract_json(buffer)
except Exception:
    sys.exit(0)

if isinstance(payload, list):
    entries = payload
else:
    entries = payload.get("result", [])

for entry in entries:
    if entry.get("title") == title:
        namespace_id = entry.get("id")
        if namespace_id:
            print(namespace_id)
            break
PY
  fi
}

# Ensure we know the namespace ID (reuse existing or create if missing)
ensure_namespace() {
  if [ -n "${CLOUDFLARE_STATE_NAMESPACE:-}" ]; then
    echo "STATE namespace already set: $CLOUDFLARE_STATE_NAMESPACE"
    return
  fi

  existing_id=$(discover_namespace_id)
  if [ -n "$existing_id" ]; then
    CLOUDFLARE_STATE_NAMESPACE="$existing_id"
    export CLOUDFLARE_STATE_NAMESPACE
    echo "Found existing STATE namespace id: $CLOUDFLARE_STATE_NAMESPACE"
    return
  fi

  echo "Creating STATE namespace '$STATE_NAMESPACE_NAME' via pywrangler ..."
  if ! output=$(uv run -- pywrangler kv namespace create "$STATE_NAMESPACE_NAME" 2>&1); then
    echo "$output"
    if echo "$output" | grep -q "already exists"; then
      echo "Namespace already exists; attempting to discover its ID..."
      existing_id=$(discover_namespace_id)
      if [ -z "$existing_id" ]; then
        echo "Unable to discover namespace id automatically; please set CLOUDFLARE_STATE_NAMESPACE manually."
        exit 1
      fi
      CLOUDFLARE_STATE_NAMESPACE="$existing_id"
      export CLOUDFLARE_STATE_NAMESPACE
      echo "Found existing namespace id: $CLOUDFLARE_STATE_NAMESPACE"
      return
    fi
    exit 1
  fi
  CLOUDFLARE_STATE_NAMESPACE=$(
    printf '%s\n' "$output" | python3 - <<'PY'
import json
import sys

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        continue
    result = payload.get("result") or {}
    namespace_id = result.get("id")
    if namespace_id:
        print(namespace_id)
        break
PY
  )
  if [ -z "$CLOUDFLARE_STATE_NAMESPACE" ]; then
    echo "Unable to parse namespace id. Please set CLOUDFLARE_STATE_NAMESPACE manually."
    exit 1
  fi
  export CLOUDFLARE_STATE_NAMESPACE
}

ensure_namespace
if [ ! -f "$TEMPLATE_PATH" ]; then
  echo "Missing wrangler template at $TEMPLATE_PATH" >&2
  exit 1
fi

if command -v envsubst >/dev/null 2>&1; then
  CLOUDFLARE_STATE_NAMESPACE="$CLOUDFLARE_STATE_NAMESPACE" envsubst < "$TEMPLATE_PATH" > "$CONFIG_PATH"
else
  sed "s/\${CLOUDFLARE_STATE_NAMESPACE}/$CLOUDFLARE_STATE_NAMESPACE/g" "$TEMPLATE_PATH" > "$CONFIG_PATH"
fi
echo "Generated wrangler.toml with STATE namespace id: $CLOUDFLARE_STATE_NAMESPACE"

# Namespace ensured above (created if missing)
echo "STATE namespace title: $STATE_NAMESPACE_NAME"
echo "STATE namespace id: $CLOUDFLARE_STATE_NAMESPACE"

echo "Setting up secrets..."
printf '%s' "${APPLE_ID:?APPLE_ID must be set}" | uv run -- pywrangler secret put APPLE_ID
printf '%s' "${APPLE_APP_PASSWORD:?APPLE_APP_PASSWORD must be set}" | uv run -- pywrangler secret put APPLE_APP_PASSWORD
printf '%s' "${NOTION_TOKEN:?NOTION_TOKEN must be set}" | uv run -- pywrangler secret put NOTION_TOKEN
printf '%s' "${ADMIN_TOKEN:?ADMIN_TOKEN must be set}" | uv run -- pywrangler secret put ADMIN_TOKEN

# Deploy the Worker (creates notion-caldav-sync if missing)
uv run -- pywrangler deploy --name notion-caldav-sync

echo "Deployment complete."
echo "Visit your worker URL and trigger /webhook/notion or wait for cron to initialize calendars."
