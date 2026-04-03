#!/bin/bash
# Hook: post-codegen-docker-lint
# Event: PostToolUse -> Write|Edit (Dockerfile)
# Purpose: Lint Dockerfile for best practices using hadolint (ECS engine only)
# Behavior: Reads JSON from stdin, checks if file_path contains "Dockerfile",
#           runs hadolint if available, gracefully skips with warning if not.
#           PostToolUse hooks are advisory -- they cannot block operations.
#
# Claude Code hook standard:
#   - Exit 0: Allow the operation to proceed
#   - Exit 2: Report error (PostToolUse treats this as non-blocking advisory)
#   - JSON on stdin: session_id, cwd, hook_event_name, tool_input, agent_id, etc.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only lint Dockerfiles
if [ -n "$FILE_PATH" ] && echo "$FILE_PATH" | grep -qi 'Dockerfile'; then
  if command -v hadolint &>/dev/null; then
    echo "Running hadolint on $FILE_PATH..."
    HADOLINT_OUTPUT=$(hadolint "$FILE_PATH" 2>&1)
    HADOLINT_EXIT=$?

    if [ $HADOLINT_EXIT -ne 0 ]; then
      echo "hadolint found Dockerfile issues:" >&2
      echo "$HADOLINT_OUTPUT" >&2
      exit 2  # Advisory error -- PostToolUse cannot block, but stderr is shown to Claude
    fi
  else
    echo "WARNING: hadolint not installed, skipping Dockerfile lint." >&2
    echo "Install hadolint for Dockerfile best-practice checks: https://github.com/hadolint/hadolint" >&2
  fi
fi

echo "HOOK PASS: Dockerfile lint passed."
exit 0  # Exit 0 = allow the operation
