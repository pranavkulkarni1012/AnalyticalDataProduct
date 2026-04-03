#!/bin/bash
# Hook: pre-config-validation
# Event: PreToolUse -> Write|Edit (YAML files)
# Purpose: Ensure no Snowflake write operations are present in config files
# Behavior: Reads JSON from stdin, checks .yaml files for SQL write statements,
#           blocks (exit 2) if Snowflake write operations are detected.
#
# Claude Code hook standard:
#   - Exit 0: Allow the operation to proceed
#   - Exit 2: Block the operation (stderr message fed back to Claude)
#   - JSON on stdin: session_id, cwd, hook_event_name, tool_input, agent_id, etc.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // empty' 2>/dev/null)

# Only check YAML config files
if [ -n "$FILE_PATH" ] && echo "$FILE_PATH" | grep -q '\.yaml$'; then
  # Check the content being written (available for Write/Edit PreToolUse)
  if [ -n "$CONTENT" ]; then
    if echo "$CONTENT" | grep -iE "(INSERT INTO|MERGE INTO|UPDATE |DELETE FROM|CREATE TABLE)" 2>/dev/null; then
      echo "BLOCKED: Config contains Snowflake write operations. Snowflake is read-only." >&2
      echo "Snowflake sources must use SELECT only. Remove any INSERT, MERGE, UPDATE, DELETE, or CREATE TABLE statements." >&2
      exit 2  # Exit 2 = block the operation (Claude Code hook standard)
    fi
  fi

  # Also check the existing file if it exists (for Edit operations)
  if [ -f "$FILE_PATH" ]; then
    if grep -iE "(INSERT INTO|MERGE INTO|UPDATE |DELETE FROM|CREATE TABLE)" "$FILE_PATH" 2>/dev/null; then
      echo "BLOCKED: Config contains Snowflake write operations. Snowflake is read-only." >&2
      echo "Snowflake sources must use SELECT only. Remove any INSERT, MERGE, UPDATE, DELETE, or CREATE TABLE statements." >&2
      exit 2  # Exit 2 = block the operation (Claude Code hook standard)
    fi
  fi
fi

exit 0  # Exit 0 = allow the operation to proceed
