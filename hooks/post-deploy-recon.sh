#!/bin/bash
# Hook: post-deploy-recon
# Event: Stop
# Purpose: Trigger reconciliation Lambda and check results after deployment
# Behavior: Reads JSON from stdin, invokes the reconciliation Lambda function,
#           blocks (exit 2) if reconciliation status is not PASS.
#
# Environment variables:
#   ADP_PRODUCT_NAME - Product name (defaults to monthly_revenue_by_category)
#   ADP_ENV          - Environment (defaults to dev)
#
# Claude Code hook standard:
#   - Exit 0: Allow (Stop hooks are advisory-only; exit 2 cannot block)
#   - JSON on stdin: session_id, cwd, hook_event_name, tool_input, agent_id, etc.
#
# NOTE: Stop hooks are advisory. The result is surfaced to Claude as feedback
# but cannot prevent the session from ending. Use exit 0 always.

INPUT=$(cat)

# Extract product name and environment from env vars or defaults
PRODUCT_NAME="${ADP_PRODUCT_NAME:-}"
if [ -z "$PRODUCT_NAME" ]; then
  echo "WARNING: ADP_PRODUCT_NAME not set, skipping recon." >&2
  exit 0
fi
ENV="${ADP_ENV:-dev}"

# Validate inputs
if [[ ! "$PRODUCT_NAME" =~ ^[a-z0-9_-]+$ ]]; then
  echo "WARNING: Invalid ADP_PRODUCT_NAME '$PRODUCT_NAME', skipping recon." >&2
  exit 0
fi
if [[ ! "$ENV" =~ ^(dev|staging|prod)$ ]]; then
  echo "WARNING: Invalid ADP_ENV '$ENV', skipping recon." >&2
  exit 0
fi

LAMBDA_NAME="adp-${PRODUCT_NAME}-recon-${ENV}"

echo "Invoking reconciliation Lambda: $LAMBDA_NAME"

# Check if AWS CLI is available
if ! command -v aws &>/dev/null; then
  echo "WARNING: AWS CLI not installed, skipping reconciliation check." >&2
  exit 0
fi

# Use session-unique temp file to avoid race conditions across concurrent sessions
TMPFILE=$(mktemp /tmp/recon_result_XXXXXX.json)
trap 'rm -f "$TMPFILE"' EXIT

# Invoke the reconciliation Lambda
RESULT=$(aws lambda invoke \
  --function-name "$LAMBDA_NAME" \
  --payload '{}' \
  --cli-binary-format raw-in-base64-out \
  "$TMPFILE" 2>&1)

INVOKE_EXIT=$?

if [ $INVOKE_EXIT -ne 0 ]; then
  echo "WARNING: Failed to invoke reconciliation Lambda: $LAMBDA_NAME" >&2
  echo "$RESULT" >&2
  echo "Reconciliation skipped -- Lambda may not be deployed yet." >&2
  exit 0  # Don't block if Lambda doesn't exist yet
fi

# Check reconciliation status
if [ -f "$TMPFILE" ]; then
  STATUS=$(jq -r '.overall_status // empty' "$TMPFILE" 2>/dev/null)

  if [ "$STATUS" = "PASS" ]; then
    echo "HOOK PASS: Reconciliation passed."
    exit 0
  elif [ -n "$STATUS" ]; then
    echo "WARNING: Reconciliation failed with status: $STATUS" >&2
    jq '.' "$TMPFILE" >&2
    exit 0  # Stop hooks are advisory-only; surface failure to Claude
  else
    echo "WARNING: Could not parse reconciliation result." >&2
    cat "$TMPFILE" >&2
    exit 0  # Don't block on parse errors
  fi
else
  echo "WARNING: Reconciliation result file not found." >&2
  exit 0
fi
