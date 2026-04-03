#!/bin/bash
# scripts/init_product.sh
# Bootstrap a new analytical data product repository.
# Usage: ./scripts/init_product.sh <product_name> <domain>
#
# Environment variables:
#   ADP_TEMPLATE_REPO  - Path to the shared template repo (optional, copies templates if set)
#
# The script is idempotent: safe to re-run without overwriting existing files.

set -euo pipefail

PRODUCT_NAME="${1:-}"
DOMAIN="${2:-}"

if [ -z "$PRODUCT_NAME" ] || [ -z "$DOMAIN" ]; then
  echo "Usage: $0 <product_name> <domain>"
  echo "  product_name: snake_case name (e.g., monthly_revenue_by_category)"
  echo "  domain:       business domain (e.g., sales_analytics)"
  exit 1
fi

# Validate product name format
if ! echo "$PRODUCT_NAME" | grep -qE '^[a-z][a-z0-9_]{2,50}$'; then
  echo "ERROR: product_name must match ^[a-z][a-z0-9_]{2,50}$ (lowercase snake_case, 3-51 chars)"
  exit 1
fi

REPO_DIR="analytical-data-product-${PRODUCT_NAME}"

echo "============================================================"
echo "Initializing analytical data product: ${PRODUCT_NAME}"
echo "Domain: ${DOMAIN}"
echo "Target directory: ${REPO_DIR}"
echo "============================================================"

# ── Create directory structure ───────────────────────────────────────

echo "Creating directory structure..."

# Claude Code skills (9 skills)
mkdir -p "${REPO_DIR}/.claude/skills"/{generate-pipeline,generate-emr-pipeline,generate-lambda-pipeline,generate-ecs-pipeline,generate-step-function,generate-terraform,validate-config,validate-connection,run-recon}

# Claude Code agents (6 agents)
mkdir -p "${REPO_DIR}/.claude/agents"/{requirement-parser,spec-generator,config-generator,pipeline-generator,infra-agent,qa-agent}

# Configs and schemas
mkdir -p "${REPO_DIR}/configs/defaults"
mkdir -p "${REPO_DIR}/schemas"

# Templates (engine-scoped)
mkdir -p "${REPO_DIR}/templates"/{common,pyspark,python}

# Hooks
mkdir -p "${REPO_DIR}/hooks"

# Pipelines (product-specific output directories)
mkdir -p "${REPO_DIR}/pipelines/${PRODUCT_NAME}"/{glue_jobs,emr_jobs,lambda_jobs,ecs_jobs,step_functions,lambdas,recon}

# Terraform modules
mkdir -p "${REPO_DIR}/terraform/modules"/{glue_job,emr_cluster,ecs_task,ecr,step_function,lambda,iam,monitoring}

# Terraform environments
mkdir -p "${REPO_DIR}/terraform/environments"/{dev,staging,prod}

# Tests
mkdir -p "${REPO_DIR}/tests/${PRODUCT_NAME}"
mkdir -p "${REPO_DIR}/tests/integration"

# Scripts, examples, harness
mkdir -p "${REPO_DIR}/scripts"
mkdir -p "${REPO_DIR}/examples"
mkdir -p "${REPO_DIR}/harness"

echo "  Directory structure created."

# ── Copy template files (if template repo is set) ───────────────────

TEMPLATE_REPO="${ADP_TEMPLATE_REPO:-}"

if [ -n "$TEMPLATE_REPO" ] && [ -d "$TEMPLATE_REPO" ]; then
  echo "Copying template files from: ${TEMPLATE_REPO}"

  # Copy skills (each SKILL.md into its own directory)
  for skill in generate-pipeline generate-emr-pipeline generate-lambda-pipeline generate-ecs-pipeline generate-step-function generate-terraform validate-config validate-connection run-recon; do
    src="${TEMPLATE_REPO}/.claude/skills/${skill}/SKILL.md"
    dst="${REPO_DIR}/.claude/skills/${skill}/SKILL.md"
    if [ -f "$src" ] && [ ! -f "$dst" ]; then
      cp "$src" "$dst"
    fi
  done

  # Copy agent definitions
  for agent in requirement-parser spec-generator config-generator pipeline-generator infra-agent qa-agent; do
    src="${TEMPLATE_REPO}/.claude/agents/${agent}/AGENT.md"
    dst="${REPO_DIR}/.claude/agents/${agent}/AGENT.md"
    if [ -f "$src" ] && [ ! -f "$dst" ]; then
      cp "$src" "$dst"
    fi
  done

  # Copy code templates (engine-scoped)
  for dir in common pyspark python; do
    if [ -d "${TEMPLATE_REPO}/templates/${dir}" ]; then
      for f in "${TEMPLATE_REPO}/templates/${dir}"/*; do
        [ -f "$f" ] || continue
        dst="${REPO_DIR}/templates/${dir}/$(basename "$f")"
        [ -f "$dst" ] || cp "$f" "$dst"
      done
    fi
  done

  # Copy hooks, schemas, and root files
  for f in "${TEMPLATE_REPO}/hooks/"*.sh; do
    [ -f "$f" ] || continue
    dst="${REPO_DIR}/hooks/$(basename "$f")"
    [ -f "$dst" ] || cp "$f" "$dst"
  done

  for f in "${TEMPLATE_REPO}/schemas/"*.json; do
    [ -f "$f" ] || continue
    dst="${REPO_DIR}/schemas/$(basename "$f")"
    [ -f "$dst" ] || cp "$f" "$dst"
  done

  for root_file in Jenkinsfile requirements.txt pyproject.toml; do
    src="${TEMPLATE_REPO}/${root_file}"
    dst="${REPO_DIR}/${root_file}"
    if [ -f "$src" ] && [ ! -f "$dst" ]; then
      cp "$src" "$dst"
    fi
  done

  echo "  Template files copied."
else
  echo "  ADP_TEMPLATE_REPO not set or not found -- skipping template copy."
  echo "  Set ADP_TEMPLATE_REPO to copy skills, agents, templates, hooks, and schemas."
fi

# ── Generate .mcp.json (Atlassian-only MCP config) ──────────────────

MCP_FILE="${REPO_DIR}/.mcp.json"
if [ ! -f "$MCP_FILE" ]; then
  cat > "$MCP_FILE" <<'MCPEOF'
{
  "mcpServers": {
    "atlassian": {
      "type": "http",
      "url": "https://mcp.atlassian.com/mcp",
      "headers": {
        "Authorization": "Bearer ${ATLASSIAN_API_TOKEN}"
      }
    }
  }
}
MCPEOF
  echo "  Generated .mcp.json (Atlassian-only MCP config)."
else
  echo "  .mcp.json already exists -- skipping."
fi

# ── Generate .claude/settings.json (hooks registration) ─────────────

SETTINGS_FILE="${REPO_DIR}/.claude/settings.json"
if [ ! -f "$SETTINGS_FILE" ]; then
  cat > "$SETTINGS_FILE" <<'SETTINGSEOF'
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$CLAUDE_PROJECT_DIR\"/hooks/pre-config-validation.sh",
            "timeout": 30,
            "statusMessage": "Validating config has no Snowflake writes..."
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$CLAUDE_PROJECT_DIR\"/hooks/pre-deploy-terraform-plan.sh",
            "timeout": 120,
            "statusMessage": "Running Terraform plan safety check..."
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$CLAUDE_PROJECT_DIR\"/hooks/post-codegen-lint.sh",
            "timeout": 60,
            "statusMessage": "Linting and security-scanning generated code..."
          },
          {
            "type": "command",
            "command": "bash \"$CLAUDE_PROJECT_DIR\"/hooks/post-codegen-docker-lint.sh",
            "timeout": 30,
            "statusMessage": "Linting Dockerfile (ECS engine)..."
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$CLAUDE_PROJECT_DIR\"/hooks/post-deploy-recon.sh",
            "timeout": 300,
            "statusMessage": "Running post-deploy reconciliation..."
          }
        ]
      }
    ]
  }
}
SETTINGSEOF
  echo "  Generated .claude/settings.json with all 5 hooks registered."
else
  echo "  .claude/settings.json already exists -- skipping."
fi

# ── Generate CLAUDE.md ──────────────────────────────────────────────

CLAUDE_FILE="${REPO_DIR}/CLAUDE.md"
if [ ! -f "$CLAUDE_FILE" ]; then
  cat > "$CLAUDE_FILE" <<EOF
# CLAUDE.md -- ${PRODUCT_NAME} Analytical Data Product

## Product Context
- Domain: ${DOMAIN}
- Owner: ${DOMAIN}-team@company.com
- Source Systems: (to be defined in config)
- Target: Iceberg table in s3://${DOMAIN}-adp-prod/${DOMAIN}/${PRODUCT_NAME}/

## Skills Available (in .claude/skills/)
- /generate-pipeline: Orchestrator -- reads compute.engine from config, delegates to engine-specific skill
- /generate-emr-pipeline: Creates PySpark EMR job from config (no GlueContext)
- /generate-lambda-pipeline: Creates Python+Pandas Lambda handler from config
- /generate-ecs-pipeline: Creates Python+Pandas ECS entrypoint + Dockerfile from config
- /generate-step-function: Creates Step Function ASL from config
- /generate-terraform: Creates Terraform modules for this product
- /validate-config: Validates pipeline config YAML against schema
- /validate-connection: Validates Snowflake connection config (OAuth, proxy, read-only)
- /run-recon: Generates reconciliation query set

## Agents Available (in .claude/agents/)
- requirement-parser: Parses Jira ticket into structured requirements JSON
- spec-generator: Generates technical spec and publishes to Confluence
- config-generator: Produces pipeline config YAML from spec
- pipeline-generator: Generates ETL code, Step Functions, and Lambdas
- infra-agent: Generates and applies Terraform infrastructure
- qa-agent: Runs reconciliation and data quality validation

## MCP Servers
Only Atlassian MCP is configured (see .mcp.json). Provides both JIRA and Confluence tools.
Do NOT add any other MCP servers.

## Hooks (in hooks/)
All hooks follow Claude Code standard: read JSON from stdin, exit 0 = allow, exit 2 = block.
- pre-config-validation.sh: Blocks Snowflake write operations in config files
- pre-deploy-terraform-plan.sh: Runs terraform plan before apply, blocks destructive changes
- post-codegen-lint.sh: Runs flake8 + bandit on generated Python code (advisory)
- post-codegen-docker-lint.sh: Runs hadolint on Dockerfiles (advisory)
- post-deploy-recon.sh: Triggers reconciliation Lambda after deployment
EOF
  echo "  Generated CLAUDE.md."
else
  echo "  CLAUDE.md already exists -- skipping."
fi

# ── Generate README.md ──────────────────────────────────────────────

README_FILE="${REPO_DIR}/README.md"
if [ ! -f "$README_FILE" ]; then
  cat > "$README_FILE" <<EOF
# ${PRODUCT_NAME} -- Analytical Data Product

**Domain:** ${DOMAIN}
**Owner:** ${DOMAIN}-team@company.com

## Overview

This repository contains the analytical data product pipeline for \`${PRODUCT_NAME}\`.
It was bootstrapped using the ADP template initialization script.

## Getting Started

1. Set your Atlassian API token:
   \`\`\`
   # In .claude/settings.local.json (gitignored)
   { "env": { "ATLASSIAN_API_TOKEN": "your-token" } }
   \`\`\`

2. Create or edit the pipeline config:
   \`\`\`
   configs/${PRODUCT_NAME}.yaml
   \`\`\`

3. Use Claude Code skills to generate pipeline code:
   \`\`\`
   /validate-config
   /generate-pipeline
   /generate-terraform
   \`\`\`

## Directory Structure

See \`CLAUDE.md\` for the full skills, agents, and hooks reference.
EOF
  echo "  Generated README.md."
else
  echo "  README.md already exists -- skipping."
fi

# ── Generate .gitignore ─────────────────────────────────────────────

GITIGNORE_FILE="${REPO_DIR}/.gitignore"
if [ ! -f "$GITIGNORE_FILE" ]; then
  cat > "$GITIGNORE_FILE" <<'EOF'
# Claude Code personal overrides (contain tokens/secrets)
CLAUDE.local.md
.claude/settings.local.json

# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
.eggs/
*.egg
.venv/
venv/

# Terraform
.terraform/
*.tfstate
*.tfstate.backup
*.tfplan
.terraform.lock.hcl

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Secrets
*.pem
*.key
.env
.env.local
EOF
  echo "  Generated .gitignore."
else
  echo "  .gitignore already exists -- skipping."
fi

# ── Done ────────────────────────────────────────────────────────────

echo ""
echo "============================================================"
echo "Product initialized at: ${REPO_DIR}"
echo "============================================================"
echo ""
echo "Next steps:"
echo "  1. cd ${REPO_DIR}"
echo "  2. git init"
echo "  3. Set ATLASSIAN_API_TOKEN in .claude/settings.local.json"
echo "  4. Create configs/${PRODUCT_NAME}.yaml (set compute.engine: glue|emr|lambda|ecs)"
echo "  5. Run /validate-config to validate your pipeline configuration"
