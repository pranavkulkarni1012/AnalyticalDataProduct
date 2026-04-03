#!/bin/bash
# Hook: post-codegen-lint
# Event: PostToolUse -> Write|Edit (.py files)
# Purpose: Run linting (flake8) and security scanning (bandit) on generated Python code
# Behavior: Reads JSON from stdin, extracts file_path, runs quality checks.
#           PostToolUse hooks are advisory -- they cannot block operations.
#           Failures are reported to stderr for Claude to review and fix.
#
# Claude Code hook standard:
#   - Exit 0: Allow the operation to proceed
#   - Exit 2: Report error (PostToolUse treats this as non-blocking advisory)
#   - JSON on stdin: session_id, cwd, hook_event_name, tool_input, agent_id, etc.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only lint Python files
if [ -n "$FILE_PATH" ] && echo "$FILE_PATH" | grep -q '\.py$'; then
  LINT_FAILED=0

  # Run flake8 if available
  if command -v flake8 &>/dev/null; then
    echo "Running flake8 on $FILE_PATH..."
    FLAKE8_OUTPUT=$(flake8 "$FILE_PATH" --max-line-length=120 --ignore=E501,W503 2>&1)
    FLAKE8_EXIT=$?

    if [ $FLAKE8_EXIT -ne 0 ]; then
      echo "flake8 found issues:" >&2
      echo "$FLAKE8_OUTPUT" >&2
      LINT_FAILED=1
    fi
  else
    echo "WARNING: flake8 not installed, skipping Python lint." >&2
  fi

  # Run bandit security scan if available
  if command -v bandit &>/dev/null; then
    echo "Running bandit (security scan) on $FILE_PATH..."
    BANDIT_OUTPUT=$(bandit "$FILE_PATH" -ll 2>&1)
    BANDIT_EXIT=$?

    if [ $BANDIT_EXIT -ne 0 ]; then
      echo "bandit found security issues:" >&2
      echo "$BANDIT_OUTPUT" >&2
      LINT_FAILED=1
    fi
  else
    echo "WARNING: bandit not installed, skipping security scan." >&2
  fi

  if [ $LINT_FAILED -ne 0 ]; then
    echo "Code quality checks failed. Please review and fix the issues above." >&2
    exit 2  # Advisory error -- PostToolUse cannot block, but stderr is shown to Claude
  fi
fi

echo "HOOK PASS: Code quality checks passed."
exit 0  # Exit 0 = allow the operation
