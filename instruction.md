# AI SDLC: Analytical Data Product -- Producer Instructions

**Version:** 1.0.0
**Last Updated:** 2026-04-04

This document explains how a data product producer can use the AI SDLC framework to build, deploy, and operate an Analytical Data Product pipeline on AWS. It covers what to clone, what inputs to provide, how to interact with Claude Code, and what outputs to expect at each stage.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Quick Start (5-Minute Setup)](#3-quick-start)
4. [What You Clone](#4-what-you-clone)
5. [Repository Structure After Bootstrap](#5-repository-structure-after-bootstrap)
6. [The AI SDLC Pipeline: Stage by Stage](#6-the-ai-sdlc-pipeline-stage-by-stage)
7. [Providing Input to Claude](#7-providing-input-to-claude)
8. [Pipeline Configuration Reference](#8-pipeline-configuration-reference)
9. [Compute Engine Selection Guide](#9-compute-engine-selection-guide)
10. [Skills Reference (Slash Commands)](#10-skills-reference)
11. [Subagent Reference](#11-subagent-reference)
12. [Hooks and Guardrails](#12-hooks-and-guardrails)
13. [CI/CD Workflow](#13-cicd-workflow)
14. [Governance Artifacts](#14-governance-artifacts)
15. [Troubleshooting](#15-troubleshooting)
16. [Security Model](#16-security-model)
17. [Review Summary](#17-review-summary)

---

## 1. Overview

The AI SDLC framework converts a business requirement (captured as a Jira ticket) into a fully deployed, governed data pipeline on AWS. The system is:

- **Config-driven** -- a single YAML file defines your entire data product
- **Template-backed** -- code is generated from battle-tested templates, not from scratch
- **Guardrailed** -- hooks enforce security and compliance at every stage
- **Multi-engine** -- supports Glue (PySpark), EMR (PySpark), Lambda (Python), and ECS (Python)

**End-to-end flow:**

```
Jira Ticket --> Parsed Requirements --> Technical Spec --> Pipeline Config (YAML)
    --> Generated ETL Code + Step Function + Terraform --> CI/CD Build & Deploy
    --> Reconciliation & Data Quality Validation --> Production Monitoring
```

Each stage is handled by a specialized Claude Code subagent. You can run the full pipeline end-to-end, or invoke individual stages as needed.

---

## 2. Prerequisites

### Tools Required

| Tool | Version | Purpose |
|------|---------|---------|
| Claude Code CLI | Latest | AI agent orchestration |
| Python | 3.11+ | ETL code, scripts, tests |
| Terraform | >= 1.5.0 | Infrastructure provisioning |
| AWS CLI | v2 | AWS interactions |
| Git | Latest | Version control |
| jq | Latest | JSON processing (used by hooks) |
| flake8 | Latest | Python linting (hook) |
| bandit | Latest | Security scanning (hook) |
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
export ADP_TEMPLATE_REPO="/path/to/AnalyticalDataProduct"  # this repo
```

---

## 3. Quick Start

```bash
# 1. Clone the template repository
git clone <repo-url> AnalyticalDataProduct
cd AnalyticalDataProduct

# 2. Bootstrap a new data product
bash scripts/init_product.sh my_product_name my_domain
cd analytical-data-product-my_product_name

# 3. Initialize git
git init && git add -A && git commit -m "Initial scaffold"

# 4. Start Claude Code
claude

# 5. Option A: Full AI SDLC from a Jira ticket
#    Tell Claude: "Run the full AI SDLC pipeline for ticket SCRUM-123"

# 5. Option B: Start from a config file
#    Edit configs/my_product_name.yaml with your pipeline definition, then:
#    /generate-pipeline configs/my_product_name.yaml
```

---

## 4. What You Clone

Clone the **AnalyticalDataProduct** repository. This is the template repository containing all framework components:

```
AnalyticalDataProduct/
  .claude/
    skills/           # 9 slash-command skills (code generation, validation, etc.)
    agents/           # 6 subagent definitions (requirement-parser, spec-generator, etc.)
    settings.json     # Hook registrations and tool permissions
  configs/            # Example pipeline config YAML
  schemas/            # JSON Schema for config validation
  templates/
    common/           # Shared: reconciliation.py, data_quality.py
    pyspark/          # Glue/EMR: boilerplate, Snowflake reader, Iceberg writer
    python/           # Lambda/ECS: handler, entrypoint, Snowflake reader, Iceberg writer, Dockerfile
  hooks/              # 5 guardrail hook scripts
  terraform/
    modules/          # 8 reusable Terraform modules
    environments/     # dev, staging, prod configurations
  tests/              # pytest framework with fixtures and test examples
  scripts/            # CLI utilities (validate, recon, smoke test, etc.)
  governance/         # Data contracts, lineage generators, dashboard templates
  harness/            # Harness CD pipeline YAML
  Jenkinsfile         # Jenkins CI pipeline
  CLAUDE.md           # AI agent instructions and hard constraints
  AI_SDLC_Plan.md    # Full architecture and design document
  AI_SDLC_Stories.md  # Implementation stories reference
```

### What the Bootstrap Script Creates

Running `scripts/init_product.sh <product_name> <domain>` creates a new directory `analytical-data-product-<product_name>/` with:

- Full directory structure matching the template
- Product-specific `CLAUDE.md` with your domain and product name
- `.claude/settings.json` with all 5 hooks registered
- `.mcp.json` with Atlassian MCP configuration
- `.gitignore` protecting sensitive files
- `README.md` with getting started instructions

The script is **idempotent** -- safe to re-run without overwriting existing files.

---

## 5. Repository Structure After Bootstrap

After running `init_product.sh monthly_revenue my_domain`, you get:

```
analytical-data-product-monthly_revenue/
  .claude/
    skills/
      generate-pipeline/SKILL.md        # Orchestrator: delegates by engine
      generate-emr-pipeline/SKILL.md    # EMR PySpark code generation
      generate-lambda-pipeline/SKILL.md # Lambda Python code generation
      generate-ecs-pipeline/SKILL.md    # ECS Python + Dockerfile generation
      generate-step-function/SKILL.md   # Step Function ASL generation
      generate-terraform/SKILL.md       # Terraform module generation
      validate-config/SKILL.md          # Config schema validation
      validate-connection/SKILL.md      # Snowflake connection validation
      run-recon/SKILL.md                # Reconciliation check generation
    agents/
      requirement-parser/AGENT.md       # Jira ticket -> requirements JSON
      spec-generator/AGENT.md           # Requirements -> technical spec
      config-generator/AGENT.md         # Spec -> pipeline config YAML
      pipeline-generator/AGENT.md       # Config -> ETL code + tests
      infra-agent/AGENT.md              # Config -> Terraform + deploy
      qa-agent/AGENT.md                 # Post-deploy validation
    settings.json                       # Hooks + permissions
  configs/
    monthly_revenue.yaml                # Your pipeline config (create this)
  schemas/
    pipeline_config_schema.json         # Validation schema
  templates/                            # Copied from template repo
  hooks/                                # 5 guardrail scripts
  terraform/                            # Modules + environment configs
  tests/                                # Test framework
  scripts/                              # Utility scripts
  pipelines/
    monthly_revenue/                    # Generated code goes here
      glue_jobs/                        # (or emr_jobs/, lambda_jobs/, ecs_jobs/)
      step_functions/
      recon/
  CLAUDE.md
  .mcp.json
  .gitignore
```

---

## 6. The AI SDLC Pipeline: Stage by Stage

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
3. Writes a structured JSON requirements file
4. Posts a summary comment back to the Jira ticket

### Stage 2: Specification (Spec Generator)

**Input:** `01-requirements.json`
**Output:** `artifacts/{run_id}/02-spec.json` + Confluence page

Tell Claude:
```
Generate a technical specification from the parsed requirements
```

The spec-generator agent:
1. Reads the requirements JSON
2. Enriches with technical details (Snowflake FQN, column types, join strategies, partition specs)
3. Publishes a formatted spec to Confluence
4. Posts a link to the Confluence page on the Jira ticket

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
3. Validates against the JSON Schema with up to 3 auto-fix attempts
4. Validates Snowflake connection settings (OAuth, proxy, role naming)

### Stage 4: Code Generation (Pipeline Generator)

**Input:** `03-config.yaml`
**Output:** `pipelines/{product_name}/` with ETL code, Step Function, test stubs

Tell Claude:
```
Generate the pipeline code from the config
```

Or use the slash command directly:
```
/generate-pipeline configs/monthly_revenue.yaml
```

The pipeline-generator agent:
1. Reads `compute.engine` from the config
2. Generates engine-specific ETL code (Glue PySpark, EMR PySpark, Lambda Python, or ECS Python + Dockerfile)
3. Generates a Step Function ASL JSON for orchestration
4. Creates pytest test stubs
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
/generate-terraform configs/monthly_revenue.yaml
```

The infra-agent agent:
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

The qa-agent agent:
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

## 7. Providing Input to Claude

### What Claude Needs From You

| Stage | Your Input | How to Provide |
|-------|-----------|----------------|
| **Intake** | Jira ticket ID | "Parse requirements from SCRUM-123" |
| **Spec** | Nothing (uses previous output) | "Generate the technical spec" |
| **Config** | Nothing, or manual config YAML | Edit `configs/{product}.yaml` or let agent generate |
| **Code Gen** | Config path | `/generate-pipeline configs/my_product.yaml` |
| **Infra** | Config path + target environment | "Deploy infrastructure for dev environment" |
| **Validation** | Config path + environment | "Run reconciliation checks on staging" |

### Writing a Config YAML Manually

If you prefer to skip Stages 1-3 and write your own config, create a file in `configs/` following this structure. Use `configs/monthly_revenue_by_category.yaml` or `examples/sample_config.yaml` as a reference.

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

sources:
  - name: my_source_table
    type: snowflake
    connection:
      account: company-prod.us-east-1
      warehouse: ANALYTICS_WH
      role: ADP_READER_ROLE
      authenticator: oauth         # MUST be oauth
      proxy:
        http_proxy: "http://corporate-proxy.company.com:8080"
        https_proxy: "http://corporate-proxy.company.com:8080"
    database: PROD_DB
    schema: MY_SCHEMA
    table: MY_TABLE
    columns:                       # list specific columns or ["*"]
      - id
      - value
      - created_date
    filters: []                    # optional WHERE conditions

transformations:
  joins: []                        # optional joins between sources
  aggregations:                    # optional aggregation logic
    group_by: []
    metrics: []
  filters: []                      # post-transform filters
  column_mappings: []              # rename/derive columns
  custom_sql: []                   # custom SQL expressions

target:
  catalog: glue_catalog
  database: my_domain_my_product_name_prod
  table: my_product_name
  s3_path: "s3://my-domain-adp-prod/my_domain/my_product_name/data/"
  format: iceberg
  write_mode: overwrite            # overwrite | append
  partition_by:
    - created_date
  sort_order: []
  table_properties:
    write.format.default: parquet
    write.parquet.compression-codec: zstd

reconciliation:
  enabled: true
  rules:
    - name: row_count_check
      type: row_count
      source_expr: "SELECT COUNT(*) FROM PROD_DB.MY_SCHEMA.MY_TABLE"
      target_expr: "SELECT COUNT(*) FROM my_domain_my_product_name_prod.my_product_name"
      tolerance_pct: 0.0

data_quality:
  checks:
    - name: id_not_null
      type: not_null
      column: id
      parameters: {}

runtime:
  timeout_minutes: 120
  max_concurrent_runs: 1
  tags:
    environment: prod
    team: my-team
  # Engine-specific fields (see Section 8)
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

## 8. Pipeline Configuration Reference

### Required Sections

| Section | Purpose | Required |
|---------|---------|----------|
| `product` | Name, domain, owner, version, schedule | Yes |
| `compute` | Engine selection (glue/emr/lambda/ecs) | Yes |
| `sources` | Snowflake source definitions (at least 1) | Yes |
| `transformations` | Joins, aggregations, filters, column mappings | Yes |
| `target` | Iceberg table on Glue Catalog with S3 path | Yes |
| `reconciliation` | Source-to-target validation rules (at least 1 rule) | Yes |
| `runtime` | Engine-specific settings (timeout, workers, memory) | Yes |
| `data_quality` | Column-level quality checks | No (recommended) |

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
  emr_release: "emr-7.0.0"
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

## 9. Compute Engine Selection Guide

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

## 10. Skills Reference

Skills are invoked as slash commands in Claude Code. Each skill performs a specific task.

| Skill | Command | Purpose |
|-------|---------|---------|
| **validate-config** | `/validate-config [config-path]` | Validate config YAML against schema |
| **validate-connection** | `/validate-connection [config-path]` | Validate Snowflake OAuth, proxy, role |
| **generate-pipeline** | `/generate-pipeline [config-path]` | Orchestrator: generates all code based on engine |
| **generate-emr-pipeline** | `/generate-emr-pipeline [config-path]` | Generate PySpark EMR job (SparkSession, no GlueContext) |
| **generate-lambda-pipeline** | `/generate-lambda-pipeline [config-path]` | Generate Python+Pandas Lambda handler |
| **generate-ecs-pipeline** | `/generate-ecs-pipeline [config-path]` | Generate Python+Pandas ECS task + Dockerfile |
| **generate-step-function** | `/generate-step-function [config-path]` | Generate Step Function ASL JSON |
| **generate-terraform** | `/generate-terraform [config-path]` | Generate Terraform modules for all infrastructure |
| **run-recon** | `/run-recon [config-path]` | Generate reconciliation check module |

**Typical workflow:**
```
/validate-config configs/my_product.yaml        # Step 1: Validate
/validate-connection configs/my_product.yaml     # Step 2: Check connection
/generate-pipeline configs/my_product.yaml       # Step 3: Generate all code
/generate-terraform configs/my_product.yaml      # Step 4: Generate infra
```

Note: `/generate-pipeline` automatically calls `/validate-config` and `/validate-connection` before generating code, so you can skip steps 1-2 if using the orchestrator.

---

## 11. Subagent Reference

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
requirement-parser ──> spec-generator ──> config-generator ──> pipeline-generator
                                                          └──> infra-agent
                                                          └──> qa-agent
```

Each agent writes its output to `artifacts/{run_id}/` with a numbered prefix (01-06) so the next agent can pick it up.

---

## 12. Hooks and Guardrails

Five hooks enforce safety constraints automatically. They fire during Claude Code operations without manual intervention.

| Hook | Event | What It Does |
|------|-------|-------------|
| **pre-config-validation.sh** | Before Write/Edit on YAML | Blocks Snowflake write operations (INSERT, MERGE, UPDATE, DELETE, CREATE) |
| **pre-deploy-terraform-plan.sh** | Before `terraform apply` | Runs `terraform plan` first; blocks if plan includes resource destruction |
| **post-codegen-lint.sh** | After Write/Edit on .py files | Runs flake8 (style) and bandit (security scan) |
| **post-codegen-docker-lint.sh** | After Write/Edit on Dockerfile | Runs hadolint (Dockerfile best practices) |
| **post-deploy-recon.sh** | On session Stop | Invokes reconciliation Lambda; blocks if checks fail |

**Hook exit codes:**
- `exit 0` = allow the operation
- `exit 2` = block the operation (PreToolUse hooks) or report advisory (PostToolUse hooks)

You do not need to run these manually. They are registered in `.claude/settings.json` and fire automatically.

---

## 13. CI/CD Workflow

### Jenkins (CI -- Build Stage)

The `Jenkinsfile` defines the build pipeline:

1. **Checkout** -- Clone the repository
2. **Validate Config** -- Schema validation via `scripts/validate_config.py`
3. **Lint** (parallel) -- flake8 (style) + bandit (security)
4. **Unit Test** -- pytest with JUnit reporting
5. **Terraform Validate** -- `terraform fmt -check` + `terraform validate` per environment
6. **Package** -- Upload artifacts to S3
7. **Terraform Plan** -- Generate and archive the plan

### Harness (CD -- Deploy Stage)

The `harness/pipeline.yaml` defines a 3-stage deployment:

| Stage | Environment | Approval | What Happens |
|-------|------------|----------|-------------|
| 1 | **DEV** | None (auto) | Terraform apply, trigger Step Function, integration test |
| 2 | **STAGING** | 1 lead engineer (24h timeout) | Terraform apply, reconciliation validation |
| 3 | **PROD** | 2 approvers: data platform lead + product owner (48h timeout) | Terraform apply, smoke test, final Jira update |

Each stage includes a rollback step if deployment fails.

---

## 14. Governance Artifacts

### Data Contract

Generated from your pipeline config:

```bash
python governance/generate_data_contract.py --config configs/my_product.yaml
```

Produces a data contract YAML with:
- Product identity and ownership
- Schema definition (column-level)
- SLA guarantees (freshness, availability, latency)
- Quality thresholds
- Source lineage and column mappings

### Static Lineage

```bash
python governance/lineage/static_lineage.py --config configs/my_product.yaml
```

Generates a lineage document tracing data flow from Snowflake sources through transformations to the Iceberg target, including column-level mappings.

### CloudWatch Dashboard

A template at `governance/templates/cloudwatch_dashboard.json` provides monitoring widgets for:
- Job execution status
- Duration trends
- Error rates
- SLA compliance

---

## 15. Troubleshooting

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

The `pre-deploy-terraform-plan.sh` hook blocks `terraform apply` if the plan includes resource destruction. Review the plan output and either:
- Adjust your config to avoid destruction
- Manually approve if destruction is intentional

### Reconciliation Fails

Check the validation report in `artifacts/{run_id}/06-validation-report.json`. Common causes:
- **Row count mismatch** -- Source filters may not match the pipeline's filters
- **Sum tolerance exceeded** -- Increase `tolerance_pct` or investigate data drift
- **Null check failure** -- Unexpected nulls in target columns

### Tests Fail

```bash
# Run tests locally
pytest tests/ -v

# Run specific test
pytest tests/monthly_revenue_by_category/test_etl.py -v
```

Tests use `moto` for AWS mocking and `local[*]` SparkSession. No real AWS credentials or Snowflake connections are needed.

---

## 16. Security Model

### Hard Constraints (Enforced by CLAUDE.md and Hooks)

| Constraint | Enforcement |
|------------|-------------|
| Snowflake is read-only | Hook blocks INSERT/UPDATE/DELETE/MERGE; role naming convention enforced |
| OAuth only for Snowflake | Config schema enforces `authenticator: oauth`; connection validation checks |
| No hardcoded secrets | Templates retrieve from Secrets Manager; hooks and code review catch violations |
| Least-privilege IAM | Terraform IAM module scopes policies to specific resources |
| Prod requires 2 approvals | Harness pipeline enforces dual approval from different user groups |
| No auto-apply in prod | Infra agent creates PR instead of applying directly |

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

## 17. Review Summary

This section summarizes the quality review of all framework deliverables.

### Epic-by-Epic Assessment

| Epic | Deliverables | Status | Grade |
|------|-------------|--------|-------|
| **1. Foundation & Guardrails** | init script, config schema, example config, 5 hooks, settings | Complete | A |
| **2. Claude Code Skills** | 9 skill definitions (SKILL.md files) | Complete | A+ |
| **3. Code Templates** | 11 template files (PySpark, Python, Dockerfile, common) | Complete | A+ |
| **4. Subagents** | 6 agent definitions (AGENT.md files) | Complete | A+ |
| **5. Terraform Modules** | 8 modules + 3 environment configs + backend configs | Complete | A+ |
| **6. CI/CD Pipelines** | Jenkinsfile + Harness pipeline YAML | Complete | A+ |
| **7. Testing & Scripts** | pytest framework + 5 utility scripts | Complete | A |
| **8. Governance** | Data contracts, lineage, dashboard templates, CLAUDE.md | Complete | A |

### Key Quality Highlights

- **Config Schema** -- Validates all 7 sections with engine-specific conditional requirements for Glue, EMR, Lambda, and ECS
- **Skills** -- All 9 skills have correct YAML frontmatter, engine-specific instructions, and proper output path conventions
- **Templates** -- All 11 templates enforce OAuth-only auth, structured logging with correlation IDs, parameterized SQL, and Iceberg format-version 2
- **Subagents** -- All 6 agents have proper MCP integration, error handling with retry/auto-fix loops, and structured artifact handoff
- **Terraform** -- Least-privilege IAM, conditional module instantiation by engine, encrypted S3 backend with DynamoDB locking
- **CI/CD** -- Jenkins parallel lint stages, Harness 3-stage deployment with escalating approvals (0 -> 1 -> 2)
- **Testing** -- Comprehensive ETL logic tests, reconciliation framework tests, and end-to-end integration tests using moto and local SparkSession
- **Hooks** -- All 5 hooks follow Claude Code standard (JSON stdin, exit 0/2), with graceful degradation for missing tools

### Naming Convention

All resources follow: `adp-{domain}-{product}-{env}[-{suffix}]`

| Resource | Example |
|----------|---------|
| S3 bucket | `sales-analytics-adp-prod` |
| Glue job | `adp-sales_analytics-monthly_revenue-prod` |
| Step Function | `adp-sales_analytics-monthly_revenue-prod` |
| IAM role | `adp-glue-sales_analytics-monthly_revenue-prod` |
| CloudWatch log group | `/adp/sales_analytics/monthly_revenue/prod` |

---

## Getting Help

- Review the example config: `configs/monthly_revenue_by_category.yaml`
- Read the full architecture: `AI_SDLC_Plan.md`
- Read the implementation stories: `AI_SDLC_Stories.md`
- Check CLAUDE.md for hard constraints and coding standards
- Run `/validate-config` and `/validate-connection` before code generation
- Use `pytest tests/ -v` to run the test suite locally
