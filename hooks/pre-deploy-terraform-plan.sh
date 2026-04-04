#!/bin/bash
# Hook: pre-deploy-terraform-plan
# Event: PreToolUse -> Bash (terraform apply)
# Purpose: Run terraform plan and check for destructive changes before apply
# Behavior: Reads JSON from stdin, extracts command, runs terraform plan,
#           blocks (exit 2) if plan fails or includes resource destruction.
#
# Claude Code hook standard:
#   - Exit 0: Allow the operation to proceed
#   - Exit 2: Block the operation (stderr message fed back to Claude)
#   - JSON on stdin: session_id, cwd, hook_event_name, tool_input, agent_id, etc.

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)

# Only check terraform apply commands -- skip all other Bash commands
if ! echo "$COMMAND" | grep -q 'terraform apply'; then
  exit 0
fi

# Extract terraform directory and environment from the command context
TERRAFORM_DIR=$(echo "$COMMAND" | grep -oP '(?<=cd\s)[^\s;]+' || echo "terraform")
ENV=$(echo "$COMMAND" | grep -oP '(?<=-var=.environment=)[^\s"]+' || echo "dev")

# Validate environment against allowlist
if [[ ! "$ENV" =~ ^(dev|staging|prod)$ ]]; then
  echo "BLOCKED: Invalid environment '$ENV'. Must be dev, staging, or prod." >&2
  exit 2
fi

cd "$TERRAFORM_DIR/environments/$ENV" || {
  echo "BLOCKED: Cannot find terraform directory: $TERRAFORM_DIR/environments/$ENV" >&2
  exit 2
}

# Initialize terraform with environment-specific backend
terraform init -backend-config="backend-$ENV.hcl" -reconfigure -input=false >/dev/null 2>&1 || {
  echo "BLOCKED: terraform init failed for environment: $ENV" >&2
  exit 2
}

PLAN_OUTPUT=$(terraform plan -detailed-exitcode -no-color 2>&1)
PLAN_EXIT=$?

if [ $PLAN_EXIT -eq 1 ]; then
  echo "BLOCKED: Terraform plan failed." >&2
  echo "$PLAN_OUTPUT" >&2
  exit 2  # Exit 2 = block the operation
fi

# Check for resource destruction
if echo "$PLAN_OUTPUT" | grep -q "will be destroyed"; then
  echo "BLOCKED: Terraform plan includes resource destruction. Manual approval required." >&2
  echo "$PLAN_OUTPUT" | grep "will be destroyed" >&2
  exit 2  # Exit 2 = block the operation
fi

echo "HOOK PASS: Terraform plan is safe to apply."
exit 0  # Exit 0 = allow the operation
