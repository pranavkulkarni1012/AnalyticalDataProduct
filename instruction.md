# AI SDLC: Analytical Data Product -- Producer Instructions

**Version:** 2.2.0
**Last Updated:** 2026-04-07

This document explains how a data product producer can use the AI SDLC framework to build, deploy, and operate an Analytical Data Product pipeline on AWS. It covers what to clone, what inputs to provide, how to interact with Claude Code, and what outputs to expect at each stage.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Quick Start](#3-quick-start)
4. [What You Clone](#4-what-you-clone)
5. [The AI SDLC Pipeline: Stage by Stage](#5-the-ai-sdlc-pipeline-stage-by-stage)
6. [Providing Input to Claude](#6-providing-input-to-claude)
7. [Pipeline Configuration Reference](#7-pipeline-configuration-reference)
8. [Compute Engine Selection Guide](#8-compute-engine-selection-guide)
9. [Skills Reference (Slash Commands)](#9-skills-reference)
10. [Subagent Reference](#10-subagent-reference)
11. [Hooks and Guardrails](#11-hooks-and-guardrails)
12. [CI/CD Workflow](#12-cicd-workflow)
13. [Generated Artifacts](#13-generated-artifacts)
14. [Troubleshooting](#14-troubleshooting)
15. [Security Model](#15-security-model)

---

## 1. Overview

The AI SDLC framework converts a business requirement (captured as a Jira ticket) into a fully deployed, governed data pipeline on AWS. The system is:

- **Config-driven** -- a single YAML file (with SQL) defines your entire data product
- **Generic pipeline** -- one shared, reusable pipeline per engine; no per-product code generation
- **SQL-driven** -- all transformation logic (CTEs, joins, aggregations) lives in the config SQL
- **Agent-driven** -- all code, infrastructure, and tests are generated on demand by skills and agents
- **Multi-engine** -- supports Glue (PySpark), EMR (PySpark), Lambda (Python), and ECS (Python)

**End-to-end flow:**

```
Jira Ticket --> Parsed Requirements --> Technical Spec --> Pipeline Config (YAML with SQL)
    --> Generic Pipeline Deployment + Step Function + Terraform --> CI/CD Build & Deploy
    --> Reconciliation & Data Quality Validation --> Production Monitoring
```

**Key principle:** Multiple data products share the SAME pipeline code. Each product has its own config file containing the SQL query. The generic pipeline reads the config at runtime, executes the SQL against Snowflake, and writes the result to Iceberg.

Each stage is handled by a specialized Claude Code subagent (all using `model: claude-opus-4-6`). You can run the full pipeline end-to-end, or invoke individual stages as needed.

---

## 2. Prerequisites

### Tools Required

| Tool | Version | Purpose |
|------|---------|---------|
| Claude Code CLI | Latest | AI agent orchestration |
| Python | 3.11+ | ETL code and tests |
| Terraform | >= 1.5.0 | Infrastructure provisioning |
| AWS CLI | v2 | AWS interactions |
| Git | Latest | Version control |
| jq | Latest | JSON processing (used by hooks) |
| flake8 | Latest | Python linting (hook) |
| bandit | Latest | Security scanning |
| hadolint | Latest (optional) | Dockerfile linting (ECS only) |
| pytest | Latest | Testing framework |

### Accounts and Access

| Service | What You Need |
|---------|---------------|
| **AWS** | Separate accounts for dev, staging, prod. IAM credentials with permissions for Glue, EMR, Lambda, ECS, Step Functions, S3, Secrets Manager, CloudWatch, SNS, EventBridge |
| **Snowflake** | Read-only OAuth credentials. OAuth token stored in AWS Secrets Manager at path `adp/snowflake/{account}/oauth` |
| **Jira** | Project access. Atlassian API token set as `ATLASSIAN_API_TOKEN` environment variable |
| **Confluence** | Space for publishing technical specifications |
| **GitHub** | Repository access for code and infrastructure PRs |
| **Jenkins** | Build server access (CI pipeline) |
| **Harness** | Deployment platform access (CD pipeline) |

### Environment Variables

```bash
export ATLASSIAN_API_TOKEN="your-atlassian-api-token"
export AWS_REGION="us-east-1"
export AWS_PROFILE="your-aws-profile"        # or use AWS_ACCESS_KEY_ID/SECRET
```

---

## 3. Quick Start

```bash
# 1. Clone the repository
git clone <repo-url> AnalyticalDataProduct
cd AnalyticalDataProduct

# 2. Start Claude Code
claude

# 3. Option A: Full AI SDLC from a Jira ticket
#    Tell Claude: "Run the full AI SDLC pipeline for ticket SCRUM-123"

# 4. Option B: Write a config manually and generate the pipeline
#    Create configs/my_product.yaml (see Section 6 for format)
#    Then run: /generate-pipeline configs/my_product.yaml
```

---

## 4. What You Clone

Clone the **AnalyticalDataProduct** repository. This is a minimal, agent-driven repo where all
code generation logic lives in skills and agents under `.claude/`.

```
AnalyticalDataProduct/
  .claude/
    skills/           # 10 slash-command skills (code generation, validation, orchestration)
    agents/           # 6 subagent definitions (requirement-parser, spec-generator, etc.)
    settings.json     # Hook registrations and tool permissions
    settings.local.json  # Local overrides (MCP permissions, allowed commands)
  CLAUDE.md           # AI agent instructions and hard constraints
  instruction.md      # This file -- producer guide
  requirements.txt    # Python dependencies
  README.md           # Project overview
```

There are no pre-existing template files, scripts, terraform modules, or test boilerplate.
Everything is generated on demand by the skills and agents when you invoke them.

### What Gets Generated at Runtime

When skills and agents run, they create these directories:

```
  configs/                    # Pipeline config YAMLs (generated by config-generator agent)
  pipelines/
    generic/{engine}/         # Generic pipeline code (generated by /generate-pipeline)
    {product}/
      step_functions/         # Step Function ASL (generated by /generate-step-function)
      tests/                  # pytest stubs (generated by pipeline-generator agent)
  terraform/
    modules/                  # IAM, Step Functions, monitoring (generated by /generate-terraform)
    environments/             # dev/, staging/, prod/ tfvars (generated by infra-agent)
  artifacts/{run_id}/         # Per-run artifacts (01-requirements through 06-validation-report)
```

---

## 5. The AI SDLC Pipeline: Stage by Stage

### Stage 1: Intake (Requirement Parser)

**Input:** Jira ticket ID (e.g., `SCRUM-123`)
**Output:** `artifacts/{run_id}/01-requirements.json`

Tell Claude:
```
Parse requirements from Jira ticket SCRUM-123
```

The requirement-parser agent:
1. Fetches the Jira ticket via Atlassian MCP
2. Extracts data sources, transformations, target, schedule, and quality requirements
3. Drafts a suggested SQL query with CTEs and fully-qualified table names
4. Writes a structured JSON requirements file
5. Posts a summary comment back to the Jira ticket

### Stage 2: Specification (Spec Generator)

**Input:** `01-requirements.json`
**Output:** `artifacts/{run_id}/02-spec.json` + Confluence page

Tell Claude:
```
Generate a technical specification from the parsed requirements
```

The spec-generator agent:
1. Reads the requirements JSON
2. Produces a production-ready SQL query (CTEs, fully-qualified table names, double-quoted identifiers)
3. Defines source connection, target Iceberg table, and reconciliation rules
4. Publishes a formatted spec to Confluence
5. Posts a link to the Confluence page on the Jira ticket

### Stage 3: Configuration (Config Generator)

**Input:** `02-spec.json`
**Output:** `artifacts/{run_id}/03-config.yaml` + `configs/{product_name}.yaml`

Tell Claude:
```
Generate the pipeline configuration from the technical spec
```

The config-generator agent:
1. Maps the spec into pipeline config YAML
2. Applies engine-specific defaults (Glue: G.2X workers, 120 min; Lambda: 3008 MB, 900 sec; etc.)
3. Validates against the JSON Schema (embedded in the `/validate-config` skill) with up to 3 auto-fix attempts
4. Validates Snowflake connection settings (OAuth, proxy, role naming)

### Stage 4: Code Generation (Pipeline Generator)

**Input:** `03-config.yaml`
**Output:** `pipelines/generic/{engine}/` + `pipelines/{product_name}/`

Tell Claude:
```
Generate the pipeline code from the config
```

Or use the slash command directly:
```
/generate-pipeline configs/my_product.yaml
```

The pipeline-generator agent:
1. Reads `compute.engine` from the config
2. Generates the generic pipeline for the selected engine (if not already generated) -- shared code, not per-product
3. Generates a Step Function ASL JSON that passes the config path to the generic pipeline
4. Creates pytest test stubs validating config integrity and SQL
5. Runs flake8 + bandit with up to 3 auto-fix attempts

### Stage 5: Infrastructure (Infra Agent)

**Input:** Config YAML + generated code
**Output:** Terraform modules + plan

Tell Claude:
```
Generate and deploy infrastructure for the pipeline
```

Or:
```
/generate-terraform configs/my_product.yaml
```

The infra-agent:
1. Generates Terraform modules (IAM, compute engine, Step Function, Lambda recon, monitoring)
2. Runs `terraform fmt` and `terraform validate`
3. Creates a Terraform plan
4. **Non-prod (dev/staging):** Auto-applies if no resource destruction
5. **Production:** Creates a GitHub PR with the plan for manual approval (never auto-applies)

### Stage 6: Validation (QA Agent)

**Input:** Config YAML + deployed pipeline
**Output:** `artifacts/{run_id}/06-validation-report.json`

Tell Claude:
```
Run validation checks on the deployed pipeline
```

The qa-agent:
1. Runs reconciliation checks (source vs target: row_count, sum, distinct_count, null_check)
2. Runs data quality checks (not_null, unique, range, regex)
3. Generates a validation report
4. Posts results to Jira
5. Transitions the Jira ticket (Done on PASS, Blocked on FAIL)

### Running the Full Pipeline

To run all stages end-to-end:

```
Run the full AI SDLC pipeline for Jira ticket SCRUM-123
```

Claude will orchestrate all 6 agents in sequence, passing artifacts between stages.

---

## 6. Providing Input to Claude

### What Claude Needs From You

| Stage | Your Input | How to Provide |
|-------|-----------|----------------|
| **Intake** | Jira ticket ID | "Parse requirements from SCRUM-123" |
| **Spec** | Nothing (uses previous output) | "Generate the technical spec" |
| **Config** | Nothing, or manual config YAML | Create `configs/{product}.yaml` or let agent generate |
| **Code Gen** | Config path | `/generate-pipeline configs/my_product.yaml` |
| **Infra** | Config path + target environment | "Deploy infrastructure for dev environment" |
| **Validation** | Config path + environment | "Run reconciliation checks on staging" |

### Writing a Config YAML Manually

If you prefer to skip Stages 1-3 and write your own config, create a file in `configs/`.

**Minimum viable config:**

```yaml
product:
  name: my_product_name            # snake_case, 3-51 chars
  domain: my_domain
  owner: team@company.com
  version: "1.0.0"
  description: "What this pipeline does"

compute:
  engine: glue                     # glue | emr | lambda | ecs
  language: pyspark                # pyspark (glue/emr) | python (lambda/ecs)

# Snowflake connection only -- tables are referenced in the SQL query below
source:
  type: snowflake
  connection:
    account: company-prod.us-east-1
    warehouse: ANALYTICS_WH
    role: ADP_READER_ROLE
    authenticator: oauth           # MUST be oauth
    proxy:
      http_proxy: "http://corporate-proxy.company.com:8080"
      https_proxy: "http://corporate-proxy.company.com:8080"

# ALL transformation logic lives here as SQL (CTEs, joins, aggregations)
# No temp tables -- use CTEs instead. Fully-qualified table names required.
# Use ${param_name} placeholders for runtime filter values.
query:
  sql: |
    WITH filtered_data AS (
        SELECT "id", "value", "created_date", "business_system_cd"
        FROM "PROD_DB"."MY_SCHEMA"."MY_TABLE"
        WHERE "created_date" = '${load_date}'
          AND "business_system_cd" = '${business_system_cd}'
    )
    SELECT
        DATE_TRUNC('month', "created_date") AS created_month,
        SUM("value")                        AS total_value,
        COUNT(*)                            AS record_count
    FROM filtered_data
    GROUP BY DATE_TRUNC('month', "created_date")
  description: "Aggregates values by month from MY_TABLE for a given load date and business system"

# Runtime parameters -- filter values passed at execution time (optional section)
# Each parameter declared here corresponds to a ${param_name} placeholder in query.sql
parameters:
  - name: load_date
    type: date
    description: "Load date to filter source data (YYYY-MM-DD)"
    required: true
  - name: business_system_cd
    type: string
    description: "Business system code to filter source data"
    required: true

target:
  catalog: glue_catalog
  database: my_domain_my_product_name_prod
  table: my_product_name
  s3_path: "s3://my-domain-adp-prod/my_domain/my_product_name/data/"
  format: iceberg
  write_mode: overwrite            # overwrite | append
  partition_by:
    - created_month
  sort_order: []
  table_properties:
    format-version: "2"
    write.format.default: parquet
    write.parquet.compression-codec: zstd

reconciliation:
  enabled: true
  rules:
    - name: row_count_check
      type: row_count
      source_expr: >
        SELECT COUNT(*)
        FROM "PROD_DB"."MY_SCHEMA"."MY_TABLE"
        WHERE "created_date" = '${load_date}'
          AND "business_system_cd" = '${business_system_cd}'
      target_expr: "SELECT COUNT(*) FROM my_domain_my_product_name_prod.my_product_name"
      tolerance_pct: 0.0

data_quality:
  checks:
    - name: value_not_null
      type: not_null
      column: total_value
      parameters: {}

runtime:
  timeout_minutes: 120
  max_concurrent_runs: 1
  tags:
    environment: prod
    team: my-team
  # Engine-specific fields (see Section 7)
  glue_version: "4.0"
  worker_type: G.2X
  num_workers: 10
```

### Validating Your Config

Before generating code, validate your config:

```
/validate-config configs/my_product.yaml
/validate-connection configs/my_product.yaml
```

---

## 7. Pipeline Configuration Reference

### Required Sections

| Section | Purpose | Required |
|---------|---------|----------|
| `product` | Name, domain, owner, version, schedule | Yes |
| `compute` | Engine selection (glue/emr/lambda/ecs) | Yes |
| `source` | Snowflake connection (account, warehouse, role, auth, proxy) | Yes |
| `query` | SQL with all transformation logic (CTEs, joins, aggregations) | Yes |
| `target` | Iceberg table on Glue Catalog with S3 path | Yes |
| `reconciliation` | Source-to-target validation rules (at least 1 rule) | Yes |
| `runtime` | Engine-specific settings (timeout, workers, memory) | Yes |
| `parameters` | Runtime filter parameters with `${param_name}` SQL placeholders | No |
| `data_quality` | Column-level quality checks | No (recommended) |

### Runtime Parameters (Optional)

Use `parameters` when your pipeline needs to filter source data by values that change per run
(e.g., a specific date, business system code, region). The column names in your SQL WHERE
clause can be anything -- `load_dt`, `bucket_dt`, `as_of_date`, `business_system_cd`, etc.

**How it works:**
1. Declare parameters in the config YAML `parameters` section
2. Use `${param_name}` placeholders in `query.sql` and reconciliation `source_expr`
3. Pass parameter values at runtime (via Step Function input, Glue job args, Lambda event, etc.)
4. The generic pipeline substitutes values safely (type-validated, SQL-escaped)

**Parameter types:**

| Type | Validation | SQL Output | Example |
|------|-----------|------------|---------|
| `string` | Any string, single-quotes escaped | `'JBP'` | `business_system_cd: JBP` |
| `date` | Must match `YYYY-MM-DD` | `'2026-03-31'` | `load_date: 2026-03-31` |
| `integer` | Must be a valid integer | `42` (no quotes) | `batch_id: 42` |
| `number` | Must be a valid number | `3.14` (no quotes) | `threshold: 3.14` |
| `boolean` | true/false/1/0/yes/no | `TRUE` or `FALSE` | `include_deleted: false` |

**Example config with parameters:**
```yaml
parameters:
  - name: load_date
    type: date
    description: "Date to filter source data"
    required: true
  - name: business_system_cd
    type: string
    description: "Business system code"
    required: true
  - name: include_deleted
    type: boolean
    description: "Include soft-deleted records"
    required: false
    default: false

query:
  sql: |
    SELECT "id", "amount", "load_dt"
    FROM "PROD_DB"."SCHEMA"."TABLE"
    WHERE "load_dt" = '${load_date}'
      AND "business_system_cd" = '${business_system_cd}'
      AND ("is_deleted" = FALSE OR '${include_deleted}' = 'TRUE')
```

**Passing parameters at runtime:**

| Engine | How to Pass | Example |
|--------|------------|---------|
| **Step Function** | `$.parameters` in execution input | `{"parameters": {"load_date": "2026-03-31", "business_system_cd": "JBP"}}` |
| **Glue** | `--parameters` job argument (JSON string) | `--parameters '{"load_date":"2026-03-31"}'` |
| **EMR** | `--parameters` CLI argument (JSON string) | `--parameters '{"load_date":"2026-03-31"}'` |
| **Lambda** | `event["parameters"]` dict | `{"parameters": {"load_date": "2026-03-31"}}` |
| **ECS** | `--parameters` CLI argument (JSON string) | `--parameters '{"load_date":"2026-03-31"}'` |

**Important notes:**
- Parameters without defaults are required -- the pipeline fails fast if they are missing
- Parameters with defaults use the default when not provided at runtime
- The same substitution is applied to reconciliation `source_expr` so recon queries match the filtered data
- `${param_name}` placeholders that don't match any declared parameter cause a validation error

### Environment (ENV)

Every pipeline accepts an `ENV` argument indicating the deployment environment (`DEV`, `TEST`, or `PROD`). This value defaults to `DEV` when running locally so pipelines are safe to test without additional configuration.

**How ENV is set:**

| Context | How ENV Is Set |
|---------|---------------|
| **Local / manual run** | Defaults to `DEV` (no action needed) |
| **Terraform deployment** | Terraform sets `ENV` on the compute resource based on the target environment |
| **Step Function execution** | Pass `"env": "DEV"` in the execution input (`$.env`) |

**Per-engine propagation:**

| Engine | How ENV Reaches the Pipeline |
|--------|------------------------------|
| **Glue** | `--ENV` job argument (set in `default_arguments` by Terraform) |
| **EMR** | `--env` CLI argument (passed via Step Function `EntryPointArguments`) |
| **Lambda** | `ENV` environment variable (set by Terraform) or `event["env"]` |
| **ECS** | `ENV` environment variable (set by Terraform on task definition) or `--env` CLI argument |

**Important notes:**
- The pipeline code always defaults to `DEV` when ENV is not provided
- Terraform automatically sets ENV to match the deployment environment (`upper(var.environment)`)
- ENV is used by the pipeline to determine environment-specific behavior (proxy settings, Snowflake database/warehouse, etc.)

### Engine-Specific Runtime Fields

**Glue (PySpark):**
```yaml
runtime:
  glue_version: "4.0"
  worker_type: G.2X          # G.1X | G.2X | G.4X | G.8X | Z.2X
  num_workers: 10             # 2-100
  timeout_minutes: 120
  extra_py_files: []
  extra_jars: []
  job_parameters: {}
```

**EMR (PySpark):**
```yaml
runtime:
  emr_release: "emr-6.15.0"
  emr_mode: serverless        # serverless | ec2
  emr_application_id: ""      # for serverless
  instance_type: m5.2xlarge   # for ec2
  instance_count: 3           # for ec2
  timeout_minutes: 180
  spark_submit_parameters: ""
```

**Lambda (Python):**
```yaml
runtime:
  lambda_memory_mb: 3008      # 128-10240
  lambda_timeout_seconds: 900  # 1-900 (max 15 min)
  python_runtime: python3.12
  timeout_minutes: 15
  lambda_layers: []
  lambda_package_type: zip    # zip | image
```

**ECS Fargate (Python):**
```yaml
runtime:
  ecs_cpu: 2048               # 256 | 512 | 1024 | 2048 | 4096
  ecs_memory: 4096            # 512-30720
  container_image: ""
  timeout_minutes: 240
  ecs_task_role: ""
  ecs_cluster: ""
```

### Reconciliation Rule Types

| Type | Purpose | Example |
|------|---------|---------|
| `row_count` | Compare row counts between source and target | Verify no data loss |
| `sum` | Compare aggregated sums | Verify financial totals match |
| `distinct_count` | Compare unique value counts | Verify cardinality preserved |
| `null_check` | Check for unexpected nulls in target | Verify data completeness |

### Data Quality Check Types

| Type | Purpose | Parameters |
|------|---------|-----------|
| `not_null` | Column has no nulls | None |
| `unique` | Column has no duplicates | None |
| `range` | Values within min/max bounds | `min`, `max` |
| `regex` | Values match a pattern | `pattern` |
| `custom` | User-defined check | `expression`, `threshold` |

---

## 8. Compute Engine Selection Guide

```
                    Dataset Size
                    |
  < 500 MB          |   500 MB - 1 GB        > 1 GB
  < 15 min runtime  |   > 15 min runtime      Any runtime
  Event-driven?     |   No Spark needed?       Complex transforms?
       |            |        |                      |
       v            |        v                      v
    Lambda          |       ECS                Glue (default)
                    |                               |
                    |                    Need custom Spark config?
                    |                    GPU workloads? > 100 GB?
                    |                               |
                    |                               v
                    |                             EMR
```

**Decision Rules:**
1. Default to **Glue** unless the workload clearly fits another engine
2. Use **Lambda** only for transforms < 500 MB that complete in < 15 minutes
3. Use **ECS** for Python workloads exceeding Lambda limits but not needing Spark
4. Use **EMR** only when Glue worker types are insufficient or GPU is needed

---

## 9. Skills Reference

Skills are invoked as slash commands in Claude Code. Each skill performs a specific task.

| Skill | Command | Purpose |
|-------|---------|---------|
| **validate-config** | `/validate-config [config-path]` | Validate config YAML against embedded schema |
| **validate-connection** | `/validate-connection [config-path]` | Validate Snowflake OAuth, proxy, role |
| **generate-pipeline** | `/generate-pipeline [config-path]` | Orchestrator: generates all code based on engine |
| **generate-emr-pipeline** | `/generate-emr-pipeline [config-path]` | Generate PySpark EMR job (SparkSession, no GlueContext) |
| **generate-lambda-pipeline** | `/generate-lambda-pipeline [config-path]` | Generate Python+Pandas Lambda handler |
| **generate-ecs-pipeline** | `/generate-ecs-pipeline [config-path]` | Generate Python+Pandas ECS task + Dockerfile |
| **generate-step-function** | `/generate-step-function [config-path]` | Generate Step Function ASL JSON |
| **generate-terraform** | `/generate-terraform [config-path]` | Generate Terraform modules for all infrastructure |
| **run-recon** | `/run-recon [config-path]` | Generate reconciliation check module |
| **run-sdlc** | `/run-sdlc <ticket-key> [--env dev\|staging\|prod] [--skip-infra] [--skip-qa]` | Run full end-to-end AI SDLC pipeline from Jira ticket |

**Typical workflow:**
```
/validate-config configs/my_product.yaml        # Step 1: Validate
/validate-connection configs/my_product.yaml     # Step 2: Check connection
/generate-pipeline configs/my_product.yaml       # Step 3: Generate all code
/generate-terraform configs/my_product.yaml      # Step 4: Generate infra
```

Note: `/generate-pipeline` automatically calls `/validate-config` and `/validate-connection` before generating code, so you can skip steps 1-2 if using the orchestrator.

---

## 10. Subagent Reference

Subagents are specialized Claude Code agents that handle complex, multi-step tasks.

| Agent | Trigger | Input | Output |
|-------|---------|-------|--------|
| **requirement-parser** | "Parse requirements from SCRUM-XX" | Jira ticket ID | `01-requirements.json` |
| **spec-generator** | "Generate technical spec" | `01-requirements.json` | `02-spec.json` + Confluence page |
| **config-generator** | "Generate pipeline config" | `02-spec.json` | `03-config.yaml` |
| **pipeline-generator** | "Generate pipeline code" | `03-config.yaml` | ETL code + Step Function + tests |
| **infra-agent** | "Deploy infrastructure" | Config + code | Terraform plan/apply + PR (for prod) |
| **qa-agent** | "Run validation checks" | Config + deployed pipeline | `06-validation-report.json` |

### Data Flow Between Agents

```
requirement-parser --> spec-generator --> config-generator --> pipeline-generator
                                                          |-> infra-agent
                                                          |-> qa-agent
```

Each agent writes its output to `artifacts/{run_id}/` with a numbered prefix (01-06) so the next agent can pick it up.

---

## 11. Hooks and Guardrails

Two hooks are registered in `.claude/settings.json` and fire automatically during Claude Code operations:

| Hook | Event | What It Does |
|------|-------|-------------|
| **Config DML guard** | Before Write/Edit on YAML files | Blocks if config content contains DML/DDL keywords (INSERT, UPDATE, DELETE, MERGE, DROP, ALTER, TRUNCATE). Snowflake is READ-ONLY. |
| **Python linter** | After Write/Edit on .py files | Runs flake8 with `--max-line-length=120 --ignore=E501,W503`. Advisory only -- does not block. |

**Hook exit codes:**
- `exit 0` = allow the operation
- `exit 2` = block the operation (PreToolUse) or report advisory (PostToolUse)

Additional guardrails are built into the skills and agents themselves:
- `/validate-config` performs 12 semantic checks including DML/DDL scanning
- `/validate-connection` blocks non-OAuth auth, write-capable roles, and missing proxy
- The infra-agent never auto-applies Terraform to production
- The pipeline-generator runs flake8 + bandit with auto-fix loops

---

## 12. CI/CD Workflow

CI/CD pipeline definitions are generated as part of the infrastructure. The framework mandates:

### Jenkins (CI -- Build Stage)

Jenkins handles the build pipeline with these stages:
1. **Checkout** -- Clone the repository
2. **Validate Config** -- Schema validation via `/validate-config`
3. **Lint** (parallel) -- flake8 (style) + bandit (security)
4. **Unit Test** -- pytest with JUnit reporting
5. **Terraform Validate** -- `terraform fmt -check` + `terraform validate` per environment
6. **Package** -- Upload artifacts to S3
7. **Terraform Plan** -- Generate and archive the plan

### Harness (CD -- Deploy Stage)

Harness handles a 3-stage deployment:

| Stage | Environment | Approval | What Happens |
|-------|------------|----------|-------------|
| 1 | **DEV** | None (auto) | Terraform apply, trigger Step Function, integration test |
| 2 | **STAGING** | 1 lead engineer (24h timeout) | Terraform apply, reconciliation validation |
| 3 | **PROD** | 2 approvers: data platform lead + product owner (48h timeout) | Terraform apply, smoke test, final Jira update |

Each stage includes a rollback step if deployment fails.

---

## 13. Generated Artifacts

When you run the full AI SDLC pipeline, these artifacts are produced:

### Per-Run Artifacts (`artifacts/{run_id}/`)

| File | Producer | Content |
|------|----------|---------|
| `01-requirements.json` | requirement-parser | Structured requirements from Jira |
| `02-spec.json` | spec-generator | Technical spec with production-ready SQL |
| `03-config.yaml` | config-generator | Validated pipeline config YAML |
| `04-code/` | pipeline-generator | Generated pipeline code and tests |
| `05-infra-state/` | infra-agent | Terraform plan output, apply results, or PR details |
| `06-validation-report.json` | qa-agent | Reconciliation and data quality results |

### Pipeline Code (`pipelines/`)

| Directory | Content | Generated by |
|-----------|---------|-------------|
| `generic/{engine}/` | Shared pipeline code (5+ files per engine) | `/generate-pipeline` |
| `{product}/step_functions/` | Step Function ASL JSON | `/generate-step-function` |
| `{product}/tests/` | pytest test stubs | pipeline-generator agent |

### Infrastructure (`terraform/`)

| Directory | Content | Generated by |
|-----------|---------|-------------|
| `modules/iam/` | IAM execution role with least-privilege policies | `/generate-terraform` |
| `modules/step_function/` | State machine resource | `/generate-terraform` |
| `modules/reconciliation_lambda/` | Reconciliation Lambda | `/generate-terraform` |
| `modules/monitoring/` | CloudWatch, SNS, EventBridge | `/generate-terraform` |
| `modules/{engine}/` | Engine-specific resources (glue_job, emr, etl_lambda, ecs_task+ecr) | `/generate-terraform` |
| `environments/{env}/` | Per-environment main.tf, variables.tf, terraform.tfvars | infra-agent |

---

## 14. Troubleshooting

### Config Validation Fails

```
/validate-config configs/my_product.yaml
```

Common issues:
- **Missing required field** -- Check all 7 top-level sections are present
- **Invalid product name** -- Must match `^[a-z][a-z0-9_]{2,50}$`
- **Wrong authenticator** -- Must be `oauth` (not `externalbrowser` or `snowflake`)
- **Missing reconciliation rules** -- At least 1 rule is mandatory
- **Invalid s3_path** -- Must start with `s3://`
- **DML/DDL in query.sql** -- Only SELECT/WITH queries allowed (Snowflake is read-only)

### Connection Validation Fails

```
/validate-connection configs/my_product.yaml
```

Common issues:
- **Non-OAuth authentication** -- Only `authenticator: oauth` is allowed
- **Missing proxy** -- Both `http_proxy` and `https_proxy` must be set
- **Write-capable role** -- Role names with `_WRITER`, `_ADMIN`, or `_OWNER` are blocked
- **Missing warehouse** -- `warehouse` field must be non-empty

### Terraform Plan Shows Destruction

The infra-agent blocks `terraform apply` if the plan includes resource destruction in non-prod.
For production, all changes go through a GitHub PR for manual review. Review the plan output and either:
- Adjust your config to avoid destruction
- Approve the PR if destruction is intentional

### Reconciliation Fails

Check the validation report in `artifacts/{run_id}/06-validation-report.json`. Common causes:
- **Row count mismatch** -- Source filters may not match the pipeline's filters
- **Sum tolerance exceeded** -- Increase `tolerance_pct` or investigate data drift
- **Null check failure** -- Unexpected nulls in target columns

### Tests Fail

The pipeline-generator agent creates test stubs at `pipelines/{product}/tests/`. Run them with:

```bash
pytest pipelines/{product}/tests/ -v
```

Tests use `moto` for AWS mocking and `local[*]` SparkSession. No real AWS credentials or Snowflake connections are needed.

---

## 15. Security Model

### Hard Constraints (Enforced by CLAUDE.md, Hooks, and Skills)

| Constraint | Enforcement |
|------------|-------------|
| Snowflake is read-only | Hook blocks DML/DDL in YAML; `/validate-config` scans query.sql; role naming enforced by `/validate-connection` |
| OAuth only for Snowflake | Config schema enforces `authenticator: oauth`; `/validate-connection` blocks alternatives |
| No hardcoded secrets | Generated code retrieves from Secrets Manager at runtime; CLAUDE.md hard constraint |
| Least-privilege IAM | `/generate-terraform` scopes IAM policies to specific resources (no wildcards on Secrets Manager) |
| Prod requires 2 approvals | Harness CD pipeline enforces dual approval from different user groups |
| No auto-apply in prod | Infra agent creates GitHub PR instead of applying directly |

### Secrets Management

All secrets are stored in AWS Secrets Manager:
- Snowflake OAuth tokens: `adp/snowflake/{account}/oauth`
- Retrieved at runtime by ETL code via boto3
- Never hardcoded, never logged, never committed

### Proxy Configuration

All Snowflake connections route through the corporate proxy:
```yaml
proxy:
  http_proxy: "http://corporate-proxy.company.com:8080"
  https_proxy: "http://corporate-proxy.company.com:8080"
```

---

## Getting Help

- Check `CLAUDE.md` for hard constraints and coding standards
- Run `/validate-config` and `/validate-connection` before code generation
- Use the minimum viable config example in Section 6 as a starting point
- Run the full pipeline from a Jira ticket: "Run the full AI SDLC pipeline for SCRUM-123"
