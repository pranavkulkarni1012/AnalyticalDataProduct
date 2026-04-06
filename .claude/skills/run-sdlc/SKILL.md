---
name: run-sdlc
description: Orchestrates the full AI SDLC pipeline from a Jira ticket through all 6 stages (parse, spec, config, code, infra, QA). Use when the user wants to run the end-to-end pipeline.
argument-hint: "<jira-ticket-key> [--env dev|staging|prod] [--skip-infra] [--skip-qa]"
allowed-tools: Read Write Bash Glob Grep Agent
---

# Skill: run-sdlc

## Description
Orchestrates the full AI SDLC pipeline end-to-end. This is the **only entry point** for
running all 6 stages from a Jira ticket to a deployed, validated pipeline. It generates
the `run_id`, spawns each agent in sequence, passes artifacts between stages, handles
failures, and cleans up intermediate files at the end.

## Why This Skill Exists
Without an explicit orchestrator, the parent conversation must improvise the sequence,
artifact paths, and error handling. This skill makes the flow deterministic and repeatable.

## Inputs
- `$ARGUMENTS`: Jira ticket key (required), optionally followed by flags:
  - `--env <env>`: Target environment (default: `dev`)
  - `--skip-infra`: Skip Stage 5 (infrastructure generation/deployment)
  - `--skip-qa`: Skip Stage 6 (validation checks)

## Steps

### Step 0: Initialize Run

1. Generate a `run_id` as a UUID4 string:
   ```bash
   python3 -c "import uuid; print(uuid.uuid4())"
   ```
2. Parse `$ARGUMENTS` to extract:
   - `ticket_key`: First argument (e.g., `SCRUM-123`). Required -- stop if missing.
   - `env`: Value after `--env` flag (default: `dev`)
   - `skip_infra`: Whether `--skip-infra` flag is present
   - `skip_qa`: Whether `--skip-qa` flag is present
3. Create the artifacts directory:
   ```bash
   mkdir -p artifacts/{run_id}
   ```
4. Log the run start:
   ```
   ========================================
   AI SDLC PIPELINE: STARTING
   Run ID:  {run_id}
   Ticket:  {ticket_key}
   Env:     {env}
   ========================================
   ```

### Step 1: Parse Requirements

Spawn the **requirement-parser** agent:

```
Agent(subagent_type="requirement-parser", prompt="""
Parse requirements from Jira ticket {ticket_key}.

Write output to: artifacts/{run_id}/01-requirements.json
Include run_id: {run_id} in the output JSON.
""")
```

**On success:** Verify `artifacts/{run_id}/01-requirements.json` exists and contains valid JSON
with `product_name` and `source_tables` fields.

**On failure:** Stop the pipeline. Log the error. Do NOT proceed -- downstream agents
need structured requirements to produce meaningful output.

### Step 2: Generate Technical Spec

Spawn the **spec-generator** agent:

```
Agent(subagent_type="spec-generator", prompt="""
Generate a technical specification from the parsed requirements.

Input:  artifacts/{run_id}/01-requirements.json
Output: artifacts/{run_id}/02-spec.json

The run_id is {run_id}. Publish the spec to Confluence and comment on Jira ticket {ticket_key}.
""")
```

**On success:** Verify `artifacts/{run_id}/02-spec.json` exists and contains `query.sql`,
`source`, and `target` fields.

**On failure:** Stop the pipeline. The spec contains the production-ready SQL query --
without it, the config generator cannot produce a valid config.

### Step 3: Generate Pipeline Config

Spawn the **config-generator** agent:

```
Agent(subagent_type="config-generator", prompt="""
Generate a validated pipeline configuration from the technical spec.

Input:  artifacts/{run_id}/02-spec.json
Output: artifacts/{run_id}/03-config.yaml
Also write a copy to: configs/{product_name}.yaml

The run_id is {run_id}. Use /validate-config and /validate-connection to validate.
""")
```

**On success:** Verify `artifacts/{run_id}/03-config.yaml` exists and is valid YAML with
all 7 required top-level sections.

Extract `product_name` and `compute.engine` from the config for use in subsequent stages:
```bash
python3 -c "
import yaml, sys
with open('artifacts/{run_id}/03-config.yaml') as f:
    config = yaml.safe_load(f)
print(f\"product_name={config['product']['name']}\")
print(f\"engine={config['compute']['engine']}\")
"
```

**On failure:** Stop the pipeline. Log the validation errors. The config is the central
artifact -- all downstream agents depend on it.

### Step 4: Generate Pipeline Code

Spawn the **pipeline-generator** agent:

```
Agent(subagent_type="pipeline-generator", prompt="""
Generate pipeline code from the validated config.

Input:  artifacts/{run_id}/03-config.yaml
The run_id is {run_id}.
Product name: {product_name}
Engine: {engine}

Deploy the generic pipeline to pipelines/generic/{engine}/.
Generate Step Function ASL to pipelines/{product_name}/step_functions/.
Generate test stubs to pipelines/{product_name}/tests/.
Copy artifacts to artifacts/{run_id}/04-code/.
""")
```

**On success:** Verify:
- `pipelines/generic/{engine}/` exists with at least 5 files
- `pipelines/{product_name}/step_functions/{product_name}_orchestrator.asl.json` exists

**On failure:** Log the error but do NOT stop. Infrastructure and QA can still proceed
with the config alone -- the pipeline code can be regenerated.

### Step 5: Generate and Deploy Infrastructure

**Skip if** `--skip-infra` flag was set. Log: "Stage 5 skipped (--skip-infra)"

Spawn the **infra-agent** agent:

```
Agent(subagent_type="infra-agent", prompt="""
Generate Terraform infrastructure and deploy to {env} environment.

Input:  artifacts/{run_id}/03-config.yaml
The run_id is {run_id}.
Target environment: {env}
Product name: {product_name}
Engine: {engine}

Generate Terraform modules to terraform/.
Run terraform fmt, validate, and plan.
For non-prod: auto-apply if no destruction.
For prod: create a GitHub PR -- NEVER auto-apply.
Write plan output to artifacts/{run_id}/05-infra-state/.
""")
```

**On success:** Log the Terraform apply result or PR URL.

**On failure:** Log the error but do NOT stop. QA can still run against an existing
deployment. Infrastructure failures are often environment-specific and may need manual
intervention.

### Step 6: Run Validation (QA)

**Skip if** `--skip-qa` flag was set. Log: "Stage 6 skipped (--skip-qa)"

Spawn the **qa-agent** agent:

```
Agent(subagent_type="qa-agent", prompt="""
Run reconciliation and data quality validation checks.

Input:  artifacts/{run_id}/03-config.yaml
The run_id is {run_id}.
Jira ticket: {ticket_key}
Product name: {product_name}

Run reconciliation checks and data quality checks.
Write results to artifacts/{run_id}/06-validation-report.json.
Post results to Jira ticket {ticket_key}.
Transition the ticket: Done on PASS, Blocked on FAIL.
""")
```

**On success:** Read the validation report and extract `overall_status`.

**On failure:** Log the error. The pipeline is complete regardless -- QA failures
indicate data issues, not pipeline failures.

### Step 7: Cleanup and Summary

1. Read the validation report (if it exists) to get `overall_status`.
2. Identify durable outputs vs intermediate artifacts:

   **Durable outputs** (keep):
   - `configs/{product_name}.yaml`
   - `pipelines/generic/{engine}/`
   - `pipelines/{product_name}/step_functions/`
   - `pipelines/{product_name}/tests/`
   - `pipelines/{product_name}/recon/` (if generated by /run-recon)
   - `terraform/` (if generated)

   **Intermediate artifacts** (can be removed):
   - `artifacts/{run_id}/01-requirements.json`
   - `artifacts/{run_id}/02-spec.json`
   - `artifacts/{run_id}/03-config.yaml` (copy exists in configs/)
   - `artifacts/{run_id}/04-code/` (copy exists in pipelines/)
   - `artifacts/{run_id}/05-infra-state/` (plan output -- keep if needed for audit)

3. Keep `artifacts/{run_id}/06-validation-report.json` as the audit trail.
4. Remove intermediate files:
   ```bash
   rm -f artifacts/{run_id}/01-requirements.json
   rm -f artifacts/{run_id}/02-spec.json
   rm -f artifacts/{run_id}/03-config.yaml
   rm -rf artifacts/{run_id}/04-code/
   ```
   Note: Keep `05-infra-state/` and `06-validation-report.json` for audit.

5. Present the final summary:

```
========================================
AI SDLC PIPELINE: COMPLETE
Run ID:  {run_id}
Ticket:  {ticket_key}
Engine:  {engine}
Env:     {env}
========================================

Stages:
  1. Requirements:  DONE
  2. Specification:  DONE (Confluence page published)
  3. Configuration:  DONE -> configs/{product_name}.yaml
  4. Pipeline Code:  DONE -> pipelines/generic/{engine}/ + pipelines/{product_name}/
  5. Infrastructure: DONE | SKIPPED | FAILED
  6. Validation:     PASS | FAIL | SKIPPED | FAILED

Durable Outputs:
  - Config:         configs/{product_name}.yaml
  - Pipeline:       pipelines/generic/{engine}/ (shared)
  - Step Function:  pipelines/{product_name}/step_functions/
  - Tests:          pipelines/{product_name}/tests/
  - Terraform:      terraform/ (if generated)
  - Audit:          artifacts/{run_id}/06-validation-report.json

Next Steps:
  - Review config: configs/{product_name}.yaml
  - Run tests: pytest pipelines/{product_name}/tests/ -v
  - Deploy via CI/CD (Jenkins build -> Harness deploy)
========================================
```

## Error Handling

| Stage | On Failure | Action |
|-------|-----------|--------|
| 1. Requirements | Stop | Cannot proceed without structured requirements |
| 2. Specification | Stop | Cannot proceed without production-ready SQL |
| 3. Configuration | Stop | Cannot proceed without validated config |
| 4. Pipeline Code | Continue | Code can be regenerated; infra/QA use config directly |
| 5. Infrastructure | Continue | Often environment-specific; may need manual fix |
| 6. Validation | Continue | QA failures = data issues, not pipeline failures |

On any failure, always log:
- Which stage failed
- The error message
- The `run_id` for troubleshooting
- Which artifacts were successfully produced before the failure
