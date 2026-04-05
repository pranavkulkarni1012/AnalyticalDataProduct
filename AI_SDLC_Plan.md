# AI SDLC Plan: Analytical Data Products in a Data Mesh on AWS

**Jira Ticket:** SCRUM-4
**Status:** Implementation Plan
**Last Updated:** 2026-04-03

---

## Table of Contents

1. [AI SDLC Architecture](#1-ai-sdlc-architecture)
2. [Claude Feature Usage by Stage](#2-claude-feature-usage-by-stage)
3. [Agent Design](#3-agent-design)
4. [Config-Driven Framework](#4-config-driven-framework)
5. [Code Generation Strategy](#5-code-generation-strategy)
6. [CI/CD Integration](#6-cicd-integration)
7. [Terraform / Infra Provisioning](#7-terraform--infra-provisioning)
8. [Standardized Claude Project Template](#8-standardized-claude-project-template)
9. [Governance & Data Mesh Alignment](#9-governance--data-mesh-alignment)
10. [Example Walkthrough](#10-example-walkthrough)

---

## 1. AI SDLC Architecture

### 1.1 High-Level Vision

The AI SDLC system uses Anthropic Claude as the orchestration brain to convert a business
requirement (captured in Jira) into a fully deployed Analytical Data Product pipeline
running on AWS. The system is config-driven, template-backed, and governed by hooks and
guardrails at every stage.

### 1.2 End-to-End Flow

```
+-------------+     +-------------+     +--------------+     +----------------+
|   INTAKE    | --> |    SPEC     | --> |    CONFIG    | --> | CODE GENERATE  |
| (Jira MCP)  |     | (Claude +   |     | (Claude +    |     | (Claude +      |
|             |     |  Confluence)|     |  Validation) |     |  Templates)    |
+-------------+     +-------------+     +--------------+     +----------------+
                                                                     |
                                                                     v
+-------------+     +-------------+     +--------------+     +----------------+
|  MONITOR    | <-- |  VALIDATE   | <-- |   DEPLOY     | <-- |    BUILD       |
| (CloudWatch,|     | (QA Agent,  |     | (Terraform + |     | (Jenkins /     |
|  Lineage)   |     |  Recon)     |     |  Step Fns)   |     |  Harness)      |
+-------------+     +-------------+     +--------------+     +----------------+
```

### 1.3 Stage Definitions

| Stage | Name | Input | Output | Owner Agent |
|-------|------|-------|--------|-------------|
| 1 | **Intake** | Jira ticket (SCRUM-4 style) | Parsed requirement object | Requirement Parser Agent |
| 2 | **Spec** | Parsed requirements | Technical specification (Confluence page + JSON) | Spec Generator Agent |
| 3 | **Config** | Technical specification | Pipeline config YAML | Config Generator Agent |
| 4 | **Code Generate** | Pipeline config YAML | ETL code (PySpark or Python), Lambdas, Step Function definitions, Terraform | Pipeline Generator Agent |
| 5 | **Build** | Generated code artifacts | Tested, packaged artifacts | CI/CD Orchestrator (Jenkins/Harness) |
| 6 | **Deploy** | Packaged artifacts + Terraform | Running infrastructure + pipeline | Infra Agent |
| 7 | **Validate** | Deployed pipeline | Reconciliation report, data quality results | QA Agent |
| 8 | **Monitor** | Running pipeline | Alerts, lineage graphs, SLA dashboards | Observability (post-deploy) |

### 1.4 Cross-Stage Agent Interaction Pattern

Agents communicate through a shared artifact store on S3 and structured JSON contracts.
No agent calls another agent directly. Instead, each stage writes its output artifact to a
well-known S3 path, and the orchestrator (Step Function or CLI driver) triggers the next
stage.

```
Orchestrator (Step Function / CLI)
  |
  |-- triggers --> Requirement Parser Agent
  |                   writes --> s3://adp-artifacts/{run_id}/01-requirements.json
  |
  |-- triggers --> Spec Generator Agent
  |                   reads  --> 01-requirements.json
  |                   writes --> s3://adp-artifacts/{run_id}/02-spec.json
  |                   writes --> Confluence page via MCP
  |
  |-- triggers --> Config Generator Agent
  |                   reads  --> 02-spec.json
  |                   writes --> s3://adp-artifacts/{run_id}/03-config.yaml
  |
  |-- triggers --> Pipeline Generator Agent
  |                   reads  --> 03-config.yaml
  |                   writes --> s3://adp-artifacts/{run_id}/04-code/
  |
  |-- triggers --> Infra Agent
  |                   reads  --> 04-code/terraform/
  |                   writes --> s3://adp-artifacts/{run_id}/05-infra-state/
  |
  |-- triggers --> QA Agent
  |                   reads  --> 03-config.yaml + deployed outputs
  |                   writes --> s3://adp-artifacts/{run_id}/06-validation-report.json
```

---

## 2. Claude Feature Usage by Stage

This section maps every Claude feature to every SDLC stage with concrete detail.

### 2.1 CLAUDE.md Usage

CLAUDE.md files provide persistent instructions that Claude reads at the start of every
session. Two levels are used:

#### Global CLAUDE.md (`~/.claude/CLAUDE.md`)

This file contains organization-wide constraints that apply to ALL analytical data product
repositories.

```markdown
# Global CLAUDE.md -- Organization AI SDLC Standards

## Identity
You are an AI SDLC agent building Analytical Data Products in a Data Mesh on AWS.

## Hard Constraints
- Snowflake is READ-ONLY. Never generate code that writes to Snowflake.
- Snowflake connections MUST use OAuth authentication and route through the corporate
  HTTP proxy. Always set `http_proxy` and `https_proxy` environment variables in any
  Snowflake connection code.
- All data products MUST write to Apache Iceberg tables on S3 via Glue Catalog.
- Only two MCP servers are available: JIRA MCP and Confluence MCP. Do not assume
  access to any other MCP servers (no GitHub MCP, no Slack MCP, etc.).
- Each producer has a separate AWS account. Never hardcode account IDs.
- Terraform must be used for ALL infrastructure. No ClickOps, no CloudFormation.
- CI/CD pipelines use Jenkins for builds and Harness for deployments. Jules is the
  AI-assisted code review layer.

## Supported Compute Engines
Four compute engines are supported. The `compute.engine` field in the pipeline config
determines which engine is used. Each has specific constraints:

### Glue (PySpark)
- All PySpark code must be compatible with AWS Glue 4.0 (Spark 3.3+).
- Use GlueContext and Job API for job lifecycle (init/commit).
- Worker types: G.1X, G.2X, G.4X, G.8X, Z.2X.
- Best for: most analytical data products, managed Spark, no cluster management.

### EMR (PySpark)
- Use EMR Serverless (preferred) or EMR on EC2 for large-scale jobs.
- EMR release must be emr-6.15.0+ (Spark 3.4+, Iceberg 1.3+).
- Do NOT use GlueContext -- use plain SparkSession for EMR jobs.
- EMR Serverless: specify application ID, not cluster ID.
- Best for: very large datasets, custom Spark tuning, long-running jobs.

### Lambda (Python + Pandas)
- Python 3.11+ runtime only.
- Hard limit: 15-minute timeout, 10 GB memory maximum.
- Use ONLY for datasets that fit in memory (< 500 MB recommended).
- Use `snowflake-connector-python` (not Spark connector) for Snowflake reads.
- Use `pyiceberg` library for Iceberg writes (not Spark).
- Package dependencies as Lambda layers or container images.
- Best for: small datasets, event-driven triggers, lightweight transforms.

### ECS Fargate (Python + Pandas)
- Use the same Python + Pandas code pattern as Lambda (shared templates).
- No timeout limit (unlike Lambda). Suitable for medium-to-large datasets.
- Container images must use the corporate base image from ECR.
- Include health check endpoints in all ECS tasks.
- Dockerfile must pass hadolint linting.
- Best for: medium datasets, long-running Python jobs, teams without Spark expertise.

## Naming Conventions
- S3 paths: s3://{account_alias}-adp-{env}/{domain}/{product_name}/
- Glue databases: {domain}_{product_name}_{env}
- Iceberg tables: {domain}_{product_name}_{env}.{table_name}
- Step Functions: adp-{domain}-{product_name}-{env}
- Glue Jobs: adp-{domain}-{product_name}-{job_name}-{env}
- EMR Applications: adp-{domain}-{product_name}-emr-{env}
- Lambda Functions: adp-{domain}-{product_name}-{function_name}-{env}
- ECS Tasks: adp-{domain}-{product_name}-ecs-{env}
- ECR Repositories: adp/{domain}/{product_name}

## Code Standards
- All ETL code must include structured logging with correlation IDs.
- PySpark jobs (Glue/EMR): All SQL must be parameterized (no string interpolation
  for table/column names -- use Spark catalog references).
- Python jobs (Lambda/ECS): Use parameterized queries with snowflake-connector-python.
  Never use f-strings for SQL construction.
- Every generated pipeline must include reconciliation checks comparing source row
  counts and aggregate sums against the target Iceberg table.
```

#### Repo-Level CLAUDE.md (`./CLAUDE.md`)

Each analytical data product repository has its own CLAUDE.md with product-specific context.

```markdown
# CLAUDE.md -- {Product Name} Analytical Data Product

## Product Context
- Domain: Sales Analytics
- Owner: sales-analytics-team@company.com
- Source Systems: Snowflake (customer_orders, product_catalog)
- Target: Iceberg table in s3://sales-adp-prod/sales/monthly_revenue/

## Repo Structure
See Section 8 of this document for the standardized template.

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

## Domain-Specific Rules
- customer_orders.order_date is in UTC; convert to US/Eastern for reporting.
- product_catalog.category uses legacy codes; map via lookup table
  s3://sales-adp-prod/lookups/category_map.csv.
```

### 2.2 Skills Design

Skills are reusable, scoped prompt instructions that Claude can invoke. In Claude Code,
skills are defined as `SKILL.md` files inside `.claude/skills/<skill-name>/` directories.
Each skill gets its own subdirectory with a `SKILL.md` file containing YAML frontmatter
(name, description, argument-hint, allowed-tools, etc.) and markdown instructions.

**Project-level skills** live in `.claude/skills/` (available to this repo).
**Global skills** live in `~/.claude/skills/` (available across all repos).

Skills are invoked as slash commands: `/generate-pipeline`, `/validate-config`, etc.
They can accept arguments via `$ARGUMENTS` or `$0`, `$1` positional placeholders.

#### Skill: `generate-pipeline`

**File:** `.claude/skills/generate-pipeline/SKILL.md`

```markdown
---
name: generate-pipeline
description: Orchestrator skill that reads compute.engine from the pipeline config and delegates to the appropriate engine-specific skill. Use when the user wants to create or regenerate ETL code from a config.
argument-hint: "[config-path]"
allowed-tools: Read Grep Glob Write Bash
---

# Skill: generate-pipeline

## Description
Orchestrator that reads the pipeline config, determines the compute engine, and delegates
to the appropriate engine-specific skill.

## Inputs
- Pipeline config YAML (path: $ARGUMENTS, or read from configs/)

## Steps
1. Read the pipeline config YAML.
2. Validate the config against the schema (invoke /validate-config first).
3. Validate the Snowflake connection (invoke /validate-connection).
4. Read `compute.engine` from the config.
5. Delegate to the engine-specific skill — deploy generic shared pipeline to `pipelines/generic/{engine}/`:
   - `glue` → Copy generic templates (`glue_job_boilerplate.py`, `snowflake_reader_spark.py`, `iceberg_writer_spark.py`, `reconciliation.py`) to `pipelines/generic/glue/`
   - `emr` → Invoke /generate-emr-pipeline (deploys to `pipelines/generic/emr/`)
   - `lambda` → Invoke /generate-lambda-pipeline (deploys to `pipelines/generic/lambda/`)
   - `ecs` → Invoke /generate-ecs-pipeline (deploys to `pipelines/generic/ecs/`)
6. Invoke /generate-step-function to create the orchestration ASL (passes `config_s3_path` per engine).
7. Pipeline code is generic and shared — NO transformation logic, reads config at runtime via `--CONFIG_PATH`.

## Output
- Generic shared pipeline code at `pipelines/generic/{engine}/`. Product-specific config at `configs/{product_name}.yaml`.
```

#### Skill: `validate-config`

**File:** `.claude/skills/validate-config/SKILL.md`

```markdown
---
name: validate-config
description: Validates a pipeline configuration YAML against the standard schema. Use before code generation or when config is modified.
argument-hint: "[config-path]"
allowed-tools: Read Grep Bash
---

# Skill: validate-config

## Description
Validates a pipeline configuration YAML against the standard schema.

## Checks
1. All required top-level keys are present (product, compute, source, query, target, reconciliation, runtime).
2. `source.connection` has: account, warehouse, role, authenticator (must be oauth).
3. `query.sql` starts with SELECT or WITH (CTE) and contains no DML/DDL keywords.
4. Target has: catalog, database, table, s3_path, write_mode, partition_by (optional).
5. Reconciliation has at least one rule with: type (row_count/sum/distinct_count/null_check), source_expr, target_expr, tolerance_pct.
6. Runtime has: timeout_minutes, plus engine-specific fields per compute.engine.
7. No Snowflake write operations exist in query SQL.

## Output
- Validation result: PASS or FAIL with list of errors.
```

#### Skill: `generate-terraform`

**File:** `.claude/skills/generate-terraform/SKILL.md`

```markdown
---
name: generate-terraform
description: Generates Terraform modules for the analytical data product infrastructure. Use when deploying or updating infra.
argument-hint: "[config-path]"
allowed-tools: Read Grep Glob Write Bash
---

# Skill: generate-terraform

## Description
Generates Terraform modules for the analytical data product infrastructure.

## Steps
1. Read the pipeline config YAML.
2. Generate the following Terraform resources:
   a. S3 bucket/prefix for the Iceberg table data.
   b. Glue Catalog database and table (Iceberg format).
   c. Glue Job definition (referencing the generated PySpark script in S3).
   d. IAM roles and policies (Glue execution role, S3 access, Secrets Manager for OAuth).
   e. Step Function state machine.
   f. Lambda functions (trigger, notification, reconciliation checker).
   g. CloudWatch log groups and metric alarms.
   h. EventBridge rule for scheduling (if cron defined in config).
3. Use the module structure:
   - terraform/modules/glue_job/
   - terraform/modules/step_function/
   - terraform/modules/iceberg_table/
   - terraform/modules/iam/
   - terraform/modules/monitoring/
4. Generate terraform/environments/{env}/main.tf with module invocations.
5. Generate terraform/environments/{env}/variables.tf and terraform.tfvars.

## Output
- Terraform files in terraform/ directory.
```

#### Skill: `generate-step-function`

**File:** `.claude/skills/generate-step-function/SKILL.md`

```markdown
---
name: generate-step-function
description: Generates an AWS Step Function (ASL JSON) that orchestrates the pipeline. Use when creating or updating orchestration.
argument-hint: "[config-path]"
allowed-tools: Read Grep Glob Write
---

# Skill: generate-step-function

## Description
Generates an AWS Step Function (ASL JSON) that orchestrates the pipeline.

## Steps
1. Read the pipeline config YAML.
2. Build the state machine:
   a. Start -> RunGlueJob (with retry 2x, backoff)
   b. RunGlueJob -> CheckReconciliation (Lambda)
   c. CheckReconciliation -> choice:
      - If PASS -> NotifySuccess (SNS)
      - If FAIL -> NotifyFailure (SNS) -> MarkFailed
3. Include error catchers on each state that route to a global error handler.
4. Write ASL JSON that passes `config_s3_path` to the generic pipeline (Glue: `--CONFIG_PATH`, EMR: `--config-path`, Lambda: `config_path` in Payload, ECS: `--config-path` in Command).

## Output
- Step Function ASL JSON file.
```

#### Skill: `run-recon`

**File:** `.claude/skills/run-recon/SKILL.md`

```markdown
---
name: run-recon
description: Generates reconciliation SQL/PySpark checks based on the reconciliation section of the config. Use after pipeline runs or during validation.
argument-hint: "[config-path]"
allowed-tools: Read Grep Glob Write Bash
---

# Skill: run-recon

## Description
Generates reconciliation SQL/PySpark checks based on the reconciliation section of the config.

## Steps
1. Read the reconciliation rules from the config.
2. For each rule, generate:
   - A source query (against Snowflake read-only).
   - A target query (against the Iceberg table via Glue Catalog).
   - A comparison expression with the tolerance threshold.
3. Generate a PySpark function that runs all checks and returns a structured report.
4. Output includes PASS/FAIL per rule and an overall status.

## Output
- Shared reconciliation module at pipelines/generic/common/reconciliation.py (or engine-specific location).
```

#### Skill: `validate-connection`

**File:** `.claude/skills/validate-connection/SKILL.md`

```markdown
---
name: validate-connection
description: Validates Snowflake connection configuration before pipeline generation. Checks OAuth, proxy, role, and account settings. Use before code generation or when connection config changes.
argument-hint: "[config-path]"
allowed-tools: Read Grep Bash
---

# Skill: validate-connection

## Description
Validates Snowflake connection configuration to catch misconfigurations before runtime.

## Checks
1. Each source has `authenticator: oauth` (no password or keypair auth).
2. Both `http_proxy` and `https_proxy` are set and non-empty.
3. Proxy URL matches the corporate pattern (http://corporate-proxy.company.com:*).
4. Account URL format is valid ({account}.{region} pattern).
5. Role name follows naming convention (ends with `_READER_ROLE` or `_READ_ROLE`).
6. No write-implying role names (e.g., `_WRITER`, `_ADMIN`, `_OWNER`).
7. Warehouse is specified and non-empty.
8. The Secrets Manager path `adp/snowflake/{account}/oauth` is referenced correctly.

## Output
- Validation result: PASS or FAIL with list of errors.
```

#### Skill: `generate-emr-pipeline`

**File:** `.claude/skills/generate-emr-pipeline/SKILL.md`

```markdown
---
name: generate-emr-pipeline
description: Generates a PySpark job for EMR (Serverless or EC2) from a pipeline config. Uses plain SparkSession without GlueContext. Use when compute.engine is emr.
argument-hint: "[config-path]"
allowed-tools: Read Grep Glob Write Bash
---

# Skill: generate-emr-pipeline

## Description
Generates a PySpark ETL job for EMR, using SparkSession directly (no GlueContext).

## Key Differences from Glue
- No GlueContext, no job.init/commit -- uses plain SparkSession.
- Iceberg catalog configured via Spark conf (same catalog settings).
- Script packaged as a standalone .py file submitted via EMR step or EMR Serverless job run.
- Entry point uses `if __name__ == "__main__"` pattern (not Glue's getResolvedOptions).
- Arguments parsed via argparse instead of getResolvedOptions.

## Steps
1. Copy generic EMR templates to `pipelines/generic/emr/`.
2. Templates are runnable code that reads config at runtime via `--config-path`.
3. Pipeline executes `config['query']['sql']` against Snowflake via Spark connector.
4. Writes result to Iceberg via `df.writeTo()`.
5. No transformation logic in pipeline code — all transforms in config SQL.

## Templates Used
- templates/pyspark/emr_job_boilerplate.py
- templates/pyspark/snowflake_reader_spark.py  (shared with Glue)
- templates/pyspark/iceberg_writer_spark.py    (shared with Glue)
- templates/common/reconciliation.py

## Output
- Generic shared pipeline at `pipelines/generic/emr/` (not per-product).
```

#### Skill: `generate-lambda-pipeline`

**File:** `.claude/skills/generate-lambda-pipeline/SKILL.md`

```markdown
---
name: generate-lambda-pipeline
description: Generates a Python+Pandas Lambda handler from a pipeline config. Uses snowflake-connector-python and pyiceberg. Use when compute.engine is lambda.
argument-hint: "[config-path]"
allowed-tools: Read Grep Glob Write Bash
---

# Skill: generate-lambda-pipeline

## Description
Generates a Python+Pandas Lambda function for lightweight ETL jobs.

## Key Differences from PySpark
- No Spark -- uses pandas DataFrames for all transformations.
- Snowflake reads via snowflake-connector-python (DBAPI, not Spark connector).
- Iceberg writes via pyiceberg library (not Spark writeTo).
- Lambda handler function signature: handler(event, context).
- 15-minute timeout and 10 GB memory limit -- validate dataset size in config.

## Steps
1. Copy generic Lambda templates to `pipelines/generic/lambda/`.
2. Templates are runnable code that reads config at runtime via `config_path` event key or `CONFIG_PATH` env var.
3. Pipeline executes `config['query']['sql']` against Snowflake via snowflake-connector-python.
4. Writes result to Iceberg via pyiceberg.
5. No transformation logic in pipeline code — all transforms in config SQL.

## Templates Used
- templates/python/lambda_handler.py
- templates/python/snowflake_reader_pandas.py
- templates/python/iceberg_writer_pyiceberg.py
- templates/common/reconciliation.py

## Output
- Generic shared pipeline at `pipelines/generic/lambda/` (not per-product).
```

#### Skill: `generate-ecs-pipeline`

**File:** `.claude/skills/generate-ecs-pipeline/SKILL.md`

```markdown
---
name: generate-ecs-pipeline
description: Generates a Python+Pandas ECS Fargate task from a pipeline config. Includes Dockerfile and entrypoint script. Use when compute.engine is ecs.
argument-hint: "[config-path]"
allowed-tools: Read Grep Glob Write Bash
---

# Skill: generate-ecs-pipeline

## Description
Generates a containerized Python+Pandas ETL job for ECS Fargate.

## Key Differences from Lambda
- No timeout limit (unlike Lambda's 15 minutes).
- Runs as a Docker container on ECS Fargate.
- Entry point is a standalone Python script (not a Lambda handler).
- Generates Dockerfile based on corporate base image.
- Suitable for medium-to-large datasets that exceed Lambda memory limits.

## Steps
1. Copy generic ECS templates to `pipelines/generic/ecs/`.
2. Templates are runnable code that reads config at runtime via `--config-path`.
3. Pipeline executes `config['query']['sql']` against Snowflake via snowflake-connector-python.
4. Writes result to Iceberg via pyiceberg.
5. Dockerfile uses corporate base image from ECR.
6. No transformation logic in pipeline code — all transforms in config SQL.

## Templates Used
- templates/python/ecs_entrypoint.py
- templates/python/Dockerfile
- templates/python/snowflake_reader_pandas.py  (shared with Lambda)
- templates/python/iceberg_writer_pyiceberg.py (shared with Lambda)
- templates/common/reconciliation.py

## Output
- Generic shared pipeline at `pipelines/generic/ecs/` (not per-product).
```

### 2.3 Subagent Structure

Subagents are specialized Claude instances scoped to a single responsibility. They are
invoked by the orchestrator and run with their own system prompt + relevant skills.

| Subagent | Responsibility | Skills Used | MCP Access |
|----------|---------------|-------------|------------|
| **Requirement Parser** | Extracts structured requirements from Jira ticket | (none -- direct parsing) | JIRA MCP |
| **Spec Generator** | Creates technical specification, publishes to Confluence | (none -- direct generation) | JIRA MCP, Confluence MCP |
| **Config Generator** | Produces validated pipeline config YAML | validate-config, validate-connection | None |
| **Pipeline Generator** | Generates ETL code (PySpark or Python), Step Functions, Lambdas | generate-pipeline, generate-emr-pipeline, generate-lambda-pipeline, generate-ecs-pipeline, generate-step-function | None |
| **Infra Agent** | Generates and plans Terraform | generate-terraform | None |
| **QA Agent** | Creates and runs reconciliation checks, data quality | run-recon, validate-config | None |

#### Subagent Definition Files

Subagents are defined using Claude Code's `AGENT.md` convention. Each agent gets its own
subdirectory inside `.claude/agents/` with an `AGENT.md` file containing YAML frontmatter
(name, description, model, tools, etc.) and markdown instructions. Claude Code auto-discovers
these agents and can invoke them via the Agent tool.

**File:** `.claude/agents/requirement-parser/AGENT.md`

```markdown
---
name: requirement-parser
description: Reads a Jira ticket via JIRA MCP and extracts a structured requirement object for the AI SDLC pipeline.
tools: "Read Write Bash mcp__atlassian__getJiraIssue mcp__atlassian__addCommentToJiraIssue"
---

# Subagent: Requirement Parser

## System Prompt
You are the Requirement Parser agent. Your job is to read a Jira ticket via the JIRA MCP
server and extract a structured requirement object.

## Input
- Jira ticket key (e.g., SCRUM-4)

## Process
1. Call JIRA MCP to fetch the ticket: title, description, acceptance criteria, labels, components.
2. Parse the description to identify:
   - Source connection details (Snowflake account, warehouse, role)
   - SQL transformation logic (CTEs, joins, aggregations, filters) to produce `suggested_sql`
   - Target table details (domain, product name, table name)
   - Data quality expectations (SLAs, thresholds)
   - Schedule requirements (frequency, cron expression)
3. Generate `suggested_sql` using CTEs with fully-qualified Snowflake table names.
4. If any required field is ambiguous, add it to an "assumptions" list.
5. Produce a structured JSON output.

## Output Schema
{
  "ticket_key": "string",
  "product_name": "string",
  "domain": "string",
  "source": {
    "type": "snowflake",
    "connection": {
      "account": "string",
      "warehouse": "string",
      "role": "string",
      "authenticator": "oauth",
      "proxy": {
        "http_proxy": "string",
        "https_proxy": "string"
      }
    }
  },
  "query": {
    "sql": "string (full SQL with CTEs, joins, aggregations using fully-qualified table names)",
    "description": "string"
  },
  "target": {
    "domain": "string",
    "product_name": "string",
    "table_name": "string",
    "write_mode": "append|overwrite",
    "partition_by": ["string"]
  },
  "schedule": {
    "frequency": "string",
    "cron": "string"
  },
  "reconciliation": {
    "rules": [{"name": "string", "type": "row_count|sum|distinct_count|null_check", "source_expr": "string", "target_expr": "string", "tolerance_pct": "number"}]
  },
  "data_quality": {
    "expectations": ["string"],
    "sla_minutes": "number"
  },
  "assumptions": ["string"]
}

## Error Handling
- If JIRA MCP is unreachable, retry 3 times with exponential backoff (2s, 4s, 8s).
- If the ticket does not exist, return error with ticket key.
- If description is empty, return error requesting manual input.
```

**File:** `.claude/agents/spec-generator/AGENT.md`

```markdown
---
name: spec-generator
description: Takes parsed requirement JSON and produces a detailed technical specification, publishing it to Confluence via MCP.
tools: "Read Write Bash mcp__atlassian__createConfluencePage mcp__atlassian__updateConfluencePage mcp__atlassian__addCommentToJiraIssue"
---

# Subagent: Spec Generator

## System Prompt
You are the Spec Generator agent. You take a parsed requirement JSON and produce a
detailed technical specification. You also publish this spec to Confluence.

## Input
- Parsed requirement JSON (from Requirement Parser)

## Process
1. Read the requirement JSON.
2. Enrich with technical details:
   - Map source tables to Snowflake fully-qualified names.
   - Define the join strategy (broadcast vs shuffle based on estimated data sizes).
   - Specify the Iceberg table schema (columns, types, partition spec).
   - Define the reconciliation approach.
   - Specify the Glue job configuration (worker type, count, timeout).
3. Produce a technical spec JSON.
4. Format the spec as a Confluence page (using Atlassian wiki markup).
5. Call Confluence MCP to create/update the page under the product's Confluence space.
6. Call JIRA MCP to add a comment to the ticket with a link to the Confluence page.

## Output
- Technical spec JSON written to artifact store.
- Confluence page created/updated.
- Jira ticket commented.

## Error Handling
- If Confluence MCP fails, write spec to local file and log a warning.
- If JIRA MCP comment fails, log warning and continue.
```

### 2.4 Hooks

Hooks are automated checks and actions that fire at specific lifecycle points. They enforce
guardrails without requiring human intervention.

#### Hook Definitions (`hooks/`)

**File:** `hooks/pre-config-validation.sh`

```bash
#!/bin/bash
# Hook: pre-config-validation
# Fires: Before Config Generator writes the final config YAML (PreToolUse on Write|Edit)
# Purpose: Ensure no Snowflake write operations are present
# Note: Claude Code hooks receive JSON on stdin with tool_input details

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only check YAML config files
if [ -n "$FILE_PATH" ] && echo "$FILE_PATH" | grep -q '\.yaml$'; then
  if grep -iE "(insert into|merge into|update |delete from|create table).*snowflake" "$FILE_PATH" 2>/dev/null; then
    echo "BLOCKED: Config contains Snowflake write operations. Snowflake is read-only." >&2
    exit 2  # Exit 2 = block the operation (Claude Code hook standard)
  fi
fi

exit 0  # Exit 0 = allow the operation to proceed
```

**File:** `hooks/pre-deploy-terraform-plan.sh`

```bash
#!/bin/bash
# Hook: pre-deploy-terraform-plan
# Fires: Before Infra Agent applies Terraform (PreToolUse on Bash with terraform apply)
# Purpose: Run terraform plan and check for destructive changes
# Note: Claude Code hooks receive JSON on stdin with tool_input details

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Extract terraform directory and environment from the command context
TERRAFORM_DIR=$(echo "$COMMAND" | grep -oP '(?<=cd\s)[^\s;]+' || echo "terraform")
ENV=$(echo "$COMMAND" | grep -oP '(?<=-var=.environment=)[^\s"]+' || echo "dev")

cd "$TERRAFORM_DIR/environments/$ENV" || { echo "BLOCKED: Cannot find terraform directory" >&2; exit 2; }

terraform init -backend-config="backend-$ENV.hcl" -reconfigure
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
```

**File:** `hooks/post-codegen-lint.sh`

```bash
#!/bin/bash
# Hook: post-codegen-lint
# Fires: After Pipeline Generator writes PySpark code (PostToolUse on Write|Edit)
# Purpose: Run linting and basic static analysis
# Note: Claude Code hooks receive JSON on stdin with tool_input details

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only lint Python files
if [ -n "$FILE_PATH" ] && echo "$FILE_PATH" | grep -q '\.py$'; then
  CODE_DIR=$(dirname "$FILE_PATH")

  echo "Running flake8..."
  flake8 "$CODE_DIR" --max-line-length=120 --ignore=E501,W503
  FLAKE8_EXIT=$?

  echo "Running bandit (security)..."
  bandit -r "$CODE_DIR" -ll
  BANDIT_EXIT=$?

  if [ $FLAKE8_EXIT -ne 0 ] || [ $BANDIT_EXIT -ne 0 ]; then
    echo "BLOCKED: Code quality checks failed." >&2
    exit 2  # Exit 2 = block the operation
  fi
fi

echo "HOOK PASS: Code quality checks passed."
exit 0  # Exit 0 = allow the operation
```

**File:** `hooks/post-deploy-recon.sh`

```bash
#!/bin/bash
# Hook: post-deploy-recon
# Fires: After Claude session completes a deploy stage (Stop event)
# Purpose: Trigger reconciliation Lambda and check results
# Note: Claude Code hooks receive JSON on stdin with session details

INPUT=$(cat)

# Extract product name and environment from session context or environment variables
PRODUCT_NAME="${ADP_PRODUCT_NAME:-monthly_revenue_by_category}"
ENV="${ADP_ENV:-dev}"
LAMBDA_NAME="adp-${PRODUCT_NAME}-recon-${ENV}"

echo "Invoking reconciliation Lambda: $LAMBDA_NAME"
RESULT=$(aws lambda invoke \
  --function-name "$LAMBDA_NAME" \
  --payload '{}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/recon_result.json 2>&1)

STATUS=$(jq -r '.overall_status' /tmp/recon_result.json)

if [ "$STATUS" != "PASS" ]; then
  echo "BLOCKED: Reconciliation failed." >&2
  jq '.' /tmp/recon_result.json >&2
  exit 2  # Exit 2 = block the operation
fi

echo "HOOK PASS: Reconciliation passed."
exit 0  # Exit 0 = allow the operation
```

**File:** `hooks/post-codegen-docker-lint.sh`

```bash
#!/bin/bash
# Hook: post-codegen-docker-lint
# Fires: After Pipeline Generator writes a Dockerfile (PostToolUse on Write|Edit)
# Purpose: Lint Dockerfile for best practices (ECS engine only)
# Note: Claude Code hooks receive JSON on stdin with tool_input details

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only lint Dockerfiles
if [ -n "$FILE_PATH" ] && echo "$FILE_PATH" | grep -qi 'Dockerfile'; then
  if command -v hadolint &>/dev/null; then
    echo "Running hadolint on $FILE_PATH..."
    HADOLINT_OUTPUT=$(hadolint "$FILE_PATH" 2>&1)
    HADOLINT_EXIT=$?

    if [ $HADOLINT_EXIT -ne 0 ]; then
      echo "BLOCKED: Dockerfile lint failed." >&2
      echo "$HADOLINT_OUTPUT" >&2
      exit 2  # Exit 2 = block the operation
    fi
  else
    echo "WARNING: hadolint not installed, skipping Dockerfile lint." >&2
  fi
fi

echo "HOOK PASS: Dockerfile lint passed."
exit 0  # Exit 0 = allow the operation
```

#### Hook Registration in Claude Code Settings

Hooks are registered in `.claude/settings.json` (shared with team) or
`.claude/settings.local.json` (personal overrides). Claude Code hooks use specific
event types (`PreToolUse`, `PostToolUse`, `Stop`, etc.) with matchers and handler arrays.

**File:** `.claude/settings.json`

```json
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
        "if": "Bash(terraform apply*)",
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
```

**How the hooks map to SDLC stages:**

| SDLC Stage | Claude Code Event | Matcher | Hook Script |
|------------|------------------|---------|-------------|
| Config Generation | `PreToolUse` | `Write\|Edit` (config files) | `pre-config-validation.sh` |
| Code Generation | `PostToolUse` | `Write\|Edit` (Python files) | `post-codegen-lint.sh` (advisory -- PostToolUse cannot block; stderr feedback prompts Claude to fix issues) |
| Code Generation (ECS) | `PostToolUse` | `Write\|Edit` (Dockerfile) | `post-codegen-docker-lint.sh` (advisory -- runs hadolint on generated Dockerfiles) |
| Deploy | `PreToolUse` | `Bash(terraform apply*)` | `pre-deploy-terraform-plan.sh` |
| Post-Deploy | `Stop` | (any) | `post-deploy-recon.sh` |

**Hook blocking behavior (Claude Code standard):**
- **Exit code 0:** Allow the operation to proceed. stdout is parsed for optional JSON output.
- **Exit code 2:** Block the operation. stdout is ignored; stderr message is fed back to Claude as the error reason.
- **Any other exit code:** Non-blocking error. stderr shown in verbose mode only.
- Hooks receive event-specific **JSON on stdin** containing: `session_id`, `cwd`, `hook_event_name`, `tool_input` (for tool events), `agent_id`, `agent_type`, and `permission_mode`.
- The `PreToolUse`, `Stop`, `SubagentStop`, `TaskCreated`, `TaskCompleted`, and `ConfigChange` events support blocking via exit code 2.
- `PostToolUse` and `PostToolUseFailure` do **not** support blocking (exit 2 is treated as non-blocking error).

> **Note:** All hook scripts in the `hooks/` directory above follow this convention -- they read
> JSON from stdin, write errors to stderr, and use exit code 2 for blocking.

### 2.5 MCP Server Integration

Only two MCP servers are available: **JIRA MCP** and **Confluence MCP**.

MCP servers are configured in **`.mcp.json`** at the project root (shared with team via git):

**File:** `.mcp.json`

```json
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
```

Personal tokens and permissions are set in `.claude/settings.local.json` (gitignored):

```json
{
  "permissions": {
    "allow": [
      "mcp__atlassian__getJiraIssue",
      "mcp__atlassian__addCommentToJiraIssue",
      "mcp__atlassian__transitionJiraIssue",
      "mcp__atlassian__getAccessibleAtlassianResources",
      "mcp__atlassian__createConfluencePage",
      "mcp__atlassian__updateConfluencePage",
      "mcp__atlassian__createConfluenceFooterComment",
      "mcp__atlassian__searchJiraIssuesUsingJql"
    ]
  },
  "env": {
    "ATLASSIAN_API_TOKEN": "your-personal-token-here"
  }
}
```

> **Constraint:** No other MCP servers may be added. Only `atlassian` (which provides
> both JIRA and Confluence tools) is configured.

#### JIRA MCP Usage by Stage

| Stage | Action | MCP Call |
|-------|--------|----------|
| Intake | Fetch ticket details | `getJiraIssue(ticket_key)` |
| Intake | Get acceptance criteria | `getJiraIssue(ticket_key)` (parse description) |
| Spec | Add comment with spec link | `addCommentToJiraIssue(ticket_key, comment)` |
| Deploy | Transition ticket to "In Progress" | `transitionJiraIssue(ticket_key, transition_id)` |
| Validate | Add validation report link | `addCommentToJiraIssue(ticket_key, comment)` |
| Validate | Transition to "Done" or "Failed" | `transitionJiraIssue(ticket_key, transition_id)` |

#### Confluence MCP Usage by Stage

| Stage | Action | MCP Call |
|-------|--------|----------|
| Spec | Create tech spec page | `createConfluencePage(space_key, title, body)` |
| Spec | Update existing spec | `updateConfluencePage(page_id, title, body, version)` |
| Deploy | Create runbook page | `createConfluencePage(space_key, title, body)` |
| Validate | Append validation results | `createConfluenceFooterComment(page_id, comment)` |

---

## 3. Agent Design

### 3.1 Agent Inventory

```
+-----------------------------------------------------------------------+
|                        ORCHESTRATOR (Step Function / CLI)               |
+-----------------------------------------------------------------------+
    |           |             |              |           |          |
    v           v             v              v           v          v
+--------+ +--------+  +-----------+  +-----------+ +-------+ +-------+
| Req.   | | Spec   |  | Config    |  | Pipeline  | | Infra | |  QA   |
| Parser | | Gen.   |  | Gen.      |  | Gen.      | | Agent | | Agent |
+--------+ +--------+  +-----------+  +-----------+ +-------+ +-------+
  |  JIRA    |  JIRA       |               |            |         |
  |  MCP     |  Confluence |               |            |         |
  |          |  MCP        |               |            |         |
  v          v             v               v            v         v
  01-req     02-spec     03-config       04-code     05-infra  06-report
  .json      .json       .yaml           /            -state/  .json
```

### 3.2 Detailed Agent Specifications

#### 3.2.1 Requirement Parser Agent

- **Trigger:** Manual (user provides Jira ticket key) or automated (Jira webhook)
- **Input:** Jira ticket key (string)
- **Process:**
  1. Fetch ticket via JIRA MCP (`getJiraIssue`)
  2. Parse title, description, acceptance criteria, labels, components, custom fields
  3. Use Claude to extract structured fields from free-text description
  4. Validate completeness (source tables, target definition, schedule)
  5. If incomplete, generate a list of clarification questions and comment on the ticket
- **Output:** `01-requirements.json`
- **Error Handling:**
  - JIRA MCP unreachable: retry 3x with exponential backoff, then fail with alert
  - Ambiguous requirements: write partial output with `"status": "needs_clarification"` and comment on Jira ticket

#### 3.2.2 Spec Generator Agent

- **Trigger:** Completion of Requirement Parser (artifact `01-requirements.json` exists)
- **Input:** `01-requirements.json`
- **Process:**
  1. Read requirements JSON
  2. Resolve Snowflake table metadata (column names, types, approximate row counts) -- this is done by reading from a metadata catalog stored in S3, NOT by querying Snowflake directly at this stage
  3. Determine join strategy based on estimated table sizes
  4. Define target Iceberg table schema
  5. Define reconciliation rules
  6. Generate Confluence page body with full spec
  7. Publish to Confluence via MCP
  8. Comment on Jira ticket with Confluence link
- **Output:** `02-spec.json` + Confluence page
- **Error Handling:**
  - Metadata catalog missing: log warning, proceed with column info from requirements only
  - Confluence MCP failure: write spec to local markdown, log warning

#### 3.2.3 Config Generator Agent

- **Trigger:** Completion of Spec Generator (artifact `02-spec.json` exists)
- **Input:** `02-spec.json`
- **Process:**
  1. Read spec JSON
  2. Map each spec element to the config schema (see Section 4)
  3. Apply defaults from the domain's default config template
  4. Run validation skill (`validate-config`)
  5. Run pre-config-validation hook
- **Output:** `03-config.yaml`
- **Error Handling:**
  - Schema validation failure: fix violations and re-validate up to 3 times
  - If unfixable, write partial config with `status: invalid` and halt

#### 3.2.4 Pipeline Generator Agent

- **Trigger:** Completion of Config Generator (artifact `03-config.yaml` exists and is valid)
- **Input:** `03-config.yaml`
- **Process:**
  1. Read config YAML
  2. Invoke `generate-pipeline` skill to produce PySpark Glue job(s)
  3. Invoke `generate-step-function` skill to produce orchestration ASL
  4. Generate Lambda functions (trigger, reconciliation checker, notification)
  5. Generate unit test stubs for each PySpark job
  6. Run post-codegen-lint hook
- **Output:** `04-code/` directory with all generated artifacts
- **Error Handling:**
  - Lint failure: auto-fix common issues (import ordering, trailing whitespace) and retry
  - Security scan failure: halt and report

#### 3.2.5 Infra Agent

- **Trigger:** Completion of Pipeline Generator (artifact `04-code/` directory exists)
- **Input:** `03-config.yaml` + `04-code/`
- **Process:**
  1. Read config for infrastructure requirements
  2. Invoke `generate-terraform` skill
  3. Run `terraform fmt` and `terraform validate`
  4. Run pre-deploy-terraform-plan hook
  5. For non-production: auto-apply. For production: create PR and wait for approval.
- **Output:** `05-infra-state/` + deployed resources
- **Error Handling:**
  - Terraform validation failure: fix and retry up to 3 times
  - Plan has destructive changes: halt and require manual approval

#### 3.2.6 QA Agent

- **Trigger:** Completion of Infra Agent + first pipeline run
- **Input:** `03-config.yaml` + pipeline execution results
- **Process:**
  1. Invoke `run-recon` skill to generate reconciliation checks
  2. Execute reconciliation against source (Snowflake) and target (Iceberg)
  3. Run data quality checks (null rates, uniqueness, value distributions)
  4. Generate validation report
  5. Comment on Jira ticket with results
  6. Transition Jira ticket to "Done" (if pass) or "Failed" (if fail)
- **Output:** `06-validation-report.json`
- **Error Handling:**
  - Reconciliation failure within tolerance: PASS with warnings
  - Reconciliation failure beyond tolerance: FAIL, halt promotion

### 3.3 Agent Retry and Error Strategy

All agents follow a consistent retry policy:

```yaml
retry_policy:
  max_retries: 3
  backoff_strategy: exponential  # 2s, 4s, 8s
  retryable_errors:
    - MCP_TIMEOUT
    - MCP_RATE_LIMIT
    - S3_THROTTLE
    - GLUE_CONCURRENT_LIMIT
  non_retryable_errors:
    - SCHEMA_VALIDATION_FAILURE
    - SECURITY_SCAN_FAILURE
    - SNOWFLAKE_WRITE_DETECTED
  on_final_failure:
    - Write error to s3://adp-artifacts/{run_id}/errors/{agent_name}.json
    - Comment on Jira ticket with error summary
    - Transition Jira ticket to "Blocked"
```

---

## 4. Config-Driven Framework

### 4.1 Config Schema Definition

The pipeline configuration YAML is the single source of truth for what a data product does.
Every agent reads from it. Below is the full schema.

```yaml
# JSON Schema (expressed in YAML for readability)
pipeline_config_schema:
  type: object
  required: [product, compute, source, query, target, reconciliation, runtime]
  additionalProperties: false
  properties:

    product:
      type: object
      required: [name, domain, owner, version, description]
      properties:
        name: { type: string, pattern: "^[a-z][a-z0-9_]{2,50}$" }
        domain: { type: string }
        owner: { type: string, format: email }
        version: { type: string, pattern: "^\\d+\\.\\d+\\.\\d+$" }
        description: { type: string }
        tags: { type: object, additionalProperties: { type: string } }
        schedule:
          type: object
          properties:
            frequency: { type: string, enum: [hourly, daily, weekly, monthly] }
            cron: { type: string }

    compute:
      type: object
      required: [engine]
      properties:
        engine:
          type: string
          enum: [glue, emr, lambda, ecs]
          description: "Compute engine for ETL execution"
        language:
          type: string
          enum: [pyspark, python]
          description: "Auto-derived: glue/emr -> pyspark, lambda/ecs -> python. Can be set explicitly."

    source:
      type: object
      description: "Snowflake connection configuration (singular). Table/column selection is in query.sql."
      required: [type, connection]
      properties:
        type: { type: string, enum: [snowflake] }
        connection:
          type: object
          required: [account, warehouse, role, authenticator]
          properties:
            account: { type: string }
            warehouse: { type: string }
            role: { type: string }
            authenticator: { type: string, enum: [oauth] }
            proxy:
              type: object
              required: [http_proxy, https_proxy]
              properties:
                http_proxy: { type: string }
                https_proxy: { type: string }

    query:
      type: object
      description: "SQL query with all transformation logic (CTEs, joins, aggregations). No temp tables."
      required: [sql]
      properties:
        sql: { type: string, minLength: 10, description: "Full SQL query starting with SELECT or WITH" }
        description: { type: string }
        parameters: { type: object, additionalProperties: { type: string } }

    target:
      type: object
      required: [catalog, database, table, s3_path, write_mode]
      properties:
        catalog: { type: string, const: "glue_catalog" }
        database: { type: string }
        table: { type: string }
        s3_path: { type: string, pattern: "^s3://" }
        format: { type: string, const: "iceberg" }
        write_mode: { type: string, enum: [append, overwrite] }
        partition_by: { type: array, items: { type: string } }
        sort_order: { type: array, items: { type: string } }
        table_properties:
          type: object
          additionalProperties: { type: string }

    reconciliation:
      type: object
      required: [rules]
      properties:
        enabled: { type: boolean, default: true }
        rules:
          type: array
          minItems: 1
          items:
            type: object
            required: [name, type, source_expr, target_expr, tolerance_pct]
            properties:
              name: { type: string }
              type: { type: string, enum: [row_count, sum, distinct_count, null_check] }
              source_expr: { type: string }
              target_expr: { type: string }
              tolerance_pct: { type: number, minimum: 0, maximum: 100 }

    data_quality:
      type: object
      properties:
        checks:
          type: array
          items:
            type: object
            required: [name, type, column]
            properties:
              name: { type: string }
              type: { type: string, enum: [not_null, unique, range, regex, custom] }
              column: { type: string }
              parameters: { type: object }

    runtime:
      type: object
      required: [timeout_minutes]
      description: "Engine-specific runtime configuration. Required fields vary by compute.engine."
      properties:
        # Common fields (all engines)
        timeout_minutes: { type: integer, minimum: 1, maximum: 2880 }
        max_concurrent_runs: { type: integer, default: 1 }
        tags: { type: object, additionalProperties: { type: string } }

        # Glue-specific (when compute.engine = glue)
        glue_version: { type: string, enum: ["4.0"] }
        worker_type: { type: string, enum: [G.1X, G.2X, G.4X, G.8X, Z.2X] }
        num_workers: { type: integer, minimum: 2, maximum: 100 }
        extra_py_files: { type: array, items: { type: string } }
        extra_jars: { type: array, items: { type: string } }
        job_parameters: { type: object, additionalProperties: { type: string } }

        # EMR-specific (when compute.engine = emr)
        emr_release: { type: string, pattern: "^emr-\\d+\\.\\d+\\.\\d+$" }
        emr_mode: { type: string, enum: [serverless, ec2], default: "serverless" }
        emr_application_id: { type: string, description: "EMR Serverless application ID (serverless mode)" }
        instance_type: { type: string, description: "EC2 instance type (ec2 mode)" }
        instance_count: { type: integer, minimum: 1, maximum: 100, description: "Number of instances (ec2 mode)" }
        spark_submit_parameters: { type: string, description: "Additional spark-submit args" }

        # Lambda-specific (when compute.engine = lambda)
        lambda_memory_mb: { type: integer, minimum: 128, maximum: 10240 }
        lambda_timeout_seconds: { type: integer, minimum: 1, maximum: 900 }
        python_runtime: { type: string, enum: ["python3.11", "python3.12"], default: "python3.11" }
        lambda_layers: { type: array, items: { type: string }, description: "Lambda layer ARNs" }
        lambda_package_type: { type: string, enum: [zip, image], default: "zip" }

        # ECS-specific (when compute.engine = ecs)
        ecs_cpu: { type: integer, enum: [256, 512, 1024, 2048, 4096], description: "Fargate CPU units" }
        ecs_memory: { type: integer, description: "Fargate memory in MB (512-30720)" }
        container_image: { type: string, description: "ECR image URI (if pre-built)" }
        ecs_task_role: { type: string, description: "IAM role ARN for the ECS task" }
        ecs_cluster: { type: string, description: "ECS cluster name (uses shared cluster if omitted)" }
```

### 4.2 Full Example Config

```yaml
# configs/monthly_revenue_by_category.yaml

product:
  name: monthly_revenue_by_category
  domain: sales_analytics
  owner: sales-analytics-team@company.com
  version: "1.0.0"
  description: >
    Joins customer_orders and product_catalog from Snowflake,
    aggregates monthly revenue by product category, and writes
    to an Iceberg table for downstream consumption.

# Compute engine selection (glue | emr | lambda | ecs)
compute:
  engine: glue          # PySpark on AWS Glue
  language: pyspark     # auto-derived from engine
  tags:
    cost_center: "CC-1234"
    data_classification: "internal"
    compliance: "SOX"
  schedule:
    frequency: daily
    cron: "0 6 * * *"  # 6 AM UTC daily

source:
  type: snowflake
  connection:
    account: company-prod.us-east-1
    warehouse: ANALYTICS_WH
    role: ADP_READER_ROLE
    authenticator: oauth
    proxy:
      http_proxy: "http://corporate-proxy.company.com:8080"
      https_proxy: "http://corporate-proxy.company.com:8080"

query:
  description: >
    Joins customer_orders and product_catalog from Snowflake,
    filters to completed orders in the last 13 months,
    and aggregates monthly revenue by product category.
  sql: |
    WITH completed_orders AS (
        SELECT
            o."order_id",
            o."product_id",
            o."order_date",
            o."quantity",
            o."total_amount"
        FROM "PROD_DB"."SALES"."CUSTOMER_ORDERS" o
        WHERE o."order_status" = 'COMPLETED'
          AND o."order_date" >= DATEADD(month, -13, CURRENT_DATE())
    ),
    enriched_orders AS (
        SELECT
            co."order_id",
            co."order_date",
            co."quantity",
            co."total_amount",
            p."category"
        FROM completed_orders co
        INNER JOIN "PROD_DB"."PRODUCTS"."PRODUCT_CATALOG" p
            ON co."product_id" = p."product_id"
    )
    SELECT
        eo."category" AS product_category,
        DATE_TRUNC('month', eo."order_date") AS revenue_month,
        SUM(eo."total_amount") AS total_revenue,
        COUNT(DISTINCT eo."order_id") AS order_count,
        AVG(eo."total_amount") AS avg_order_value,
        SUM(eo."quantity") AS total_units_sold
    FROM enriched_orders eo
    GROUP BY eo."category", DATE_TRUNC('month', eo."order_date")
    HAVING SUM(eo."total_amount") > 0

target:
  catalog: glue_catalog
  database: sales_analytics_monthly_revenue_prod
  table: monthly_revenue_by_category
  s3_path: "s3://sales-adp-prod/sales_analytics/monthly_revenue_by_category/data/"
  format: iceberg
  write_mode: overwrite
  partition_by:
    - revenue_month
  sort_order:
    - product_category
  table_properties:
    write.format.default: parquet
    write.parquet.compression-codec: zstd
    write.metadata.delete-after-commit.enabled: "true"
    write.metadata.previous-versions-max: "10"

reconciliation:
  enabled: true
  rules:
    - name: total_revenue_check
      type: sum
      source_expr: >
        SELECT SUM(total_amount) FROM PROD_DB.SALES.CUSTOMER_ORDERS
        WHERE order_status = 'COMPLETED'
        AND order_date >= DATEADD(month, -13, CURRENT_DATE())
      target_expr: >
        SELECT SUM(total_revenue)
        FROM sales_analytics_monthly_revenue_prod.monthly_revenue_by_category
      tolerance_pct: 0.01

    - name: row_count_reasonableness
      type: row_count
      source_expr: >
        SELECT COUNT(DISTINCT DATE_TRUNC('month', order_date) || '-' || p.category)
        FROM PROD_DB.SALES.CUSTOMER_ORDERS o
        INNER JOIN PROD_DB.PRODUCTS.PRODUCT_CATALOG p ON o.product_id = p.product_id
        WHERE o.order_status = 'COMPLETED'
        AND o.order_date >= DATEADD(month, -13, CURRENT_DATE())
      target_expr: >
        SELECT COUNT(*)
        FROM sales_analytics_monthly_revenue_prod.monthly_revenue_by_category
      tolerance_pct: 0.0

    - name: no_null_categories
      type: null_check
      source_expr: "N/A"
      target_expr: >
        SELECT COUNT(*) FROM sales_analytics_monthly_revenue_prod.monthly_revenue_by_category
        WHERE product_category IS NULL
      tolerance_pct: 0.0

data_quality:
  checks:
    - name: revenue_positive
      type: range
      column: total_revenue
      parameters:
        min: 0
    - name: category_not_null
      type: not_null
      column: product_category
    - name: month_not_null
      type: not_null
      column: revenue_month
    - name: order_count_positive
      type: range
      column: order_count
      parameters:
        min: 1

runtime:
  glue_version: "4.0"
  worker_type: G.2X
  num_workers: 10
  timeout_minutes: 120
  max_concurrent_runs: 1
  extra_py_files:
    - "s3://sales-adp-prod/libs/adp_common-1.0.0-py3-none-any.whl"
  extra_jars:
    - "s3://sales-adp-prod/jars/iceberg-spark-runtime-3.3_2.12-1.4.2.jar"
  job_parameters:
    "--conf": "spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog"
    "--conf spark.sql.catalog.glue_catalog.warehouse": "s3://sales-adp-prod/sales_analytics/"
    "--conf spark.sql.catalog.glue_catalog.catalog-impl": "org.apache.iceberg.aws.glue.GlueCatalog"
    "--conf spark.sql.catalog.glue_catalog.io-impl": "org.apache.iceberg.aws.s3.S3FileIO"
  tags:
    environment: prod
    team: sales-analytics
    cost_center: "CC-1234"
```

---

## 5. Code Generation Strategy

### 5.1 Template Library

Templates are **generic, runnable Python files** with NO `{{ placeholders }}`. They read the
pipeline config YAML at runtime and execute the SQL query from the config against Snowflake.
Multiple data products share the SAME pipeline code — only the config differs.
Templates are organized into engine-scoped directories under `templates/`:

```
templates/
  common/                          # Shared across all engines
    reconciliation.py              # Source vs target comparison framework
    data_quality.py                # Data quality check framework
  pyspark/                         # Shared by Glue + EMR engines
    glue_job_boilerplate.py        # Glue-specific: GlueContext, job.init/commit
    emr_job_boilerplate.py         # EMR-specific: plain SparkSession, argparse entry
    snowflake_reader_spark.py      # Spark Snowflake connector (OAuth + proxy)
    iceberg_writer_spark.py        # Spark writeTo() Iceberg API
  python/                          # Shared by Lambda + ECS engines
    lambda_handler.py              # Lambda handler function skeleton
    ecs_entrypoint.py              # ECS containerized entry point (main.py)
    Dockerfile                     # ECS Dockerfile (corporate base image)
    snowflake_reader_pandas.py     # snowflake-connector-python + pandas
    iceberg_writer_pyiceberg.py    # pyiceberg Table API for Iceberg writes
```

**Engine-to-template mapping:**

| Engine | Boilerplate | Snowflake Reader | Iceberg Writer | Reconciliation |
|--------|------------|------------------|----------------|----------------|
| Glue | `pyspark/glue_job_boilerplate.py` | `pyspark/snowflake_reader_spark.py` | `pyspark/iceberg_writer_spark.py` | `common/reconciliation.py` |
| EMR | `pyspark/emr_job_boilerplate.py` | `pyspark/snowflake_reader_spark.py` | `pyspark/iceberg_writer_spark.py` | `common/reconciliation.py` |
| Lambda | `python/lambda_handler.py` | `python/snowflake_reader_pandas.py` | `python/iceberg_writer_pyiceberg.py` | `common/reconciliation.py` |
| ECS | `python/ecs_entrypoint.py` + `python/Dockerfile` | `python/snowflake_reader_pandas.py` | `python/iceberg_writer_pyiceberg.py` | `common/reconciliation.py` |

> **Key reuse:** Glue and EMR share the same Snowflake reader and Iceberg writer templates
> (both use Spark). Lambda and ECS share the same Pandas-based templates. Reconciliation
> logic is shared across all engines.

The following sections show the **PySpark templates** (Glue engine) in detail. The Pandas-based
templates (Lambda/ECS) follow the same logical structure using `snowflake-connector-python`
for reads and `pyiceberg` for writes instead of Spark APIs.

#### Template: `templates/pyspark/glue_job_boilerplate.py`

```python
"""
Generic AWS Glue PySpark ETL Job

A config-driven Glue job that reads a YAML pipeline config at runtime,
executes the SQL query from the config against Snowflake, and writes
the result to an Apache Iceberg table on S3 via the AWS Glue Catalog.

Multiple data products share this SAME code -- only the config differs.
"""
import sys, os, logging, uuid, json, re, tempfile
import boto3, yaml
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext

from snowflake_reader_spark import setup_proxy, get_oauth_token, build_sf_options, run_query
from iceberg_writer_spark import write_to_iceberg
from reconciliation import run_reconciliation

# Accepts --CONFIG_PATH, --ENV, --correlation_id from Step Function
args = getResolvedOptions(sys.argv, ["JOB_NAME", "CONFIG_PATH", "ENV", "correlation_id"])
config_path = args["CONFIG_PATH"]
env = args["ENV"]
correlation_id = args.get("correlation_id") or str(uuid.uuid4())

# Initialize Glue job, load config, validate SQL, execute query, write to Iceberg
# See templates/pyspark/glue_job_boilerplate.py for full implementation
```

#### Template: `templates/pyspark/snowflake_reader_spark.py`

```python
"""
Snowflake Reader for PySpark (Spark Connector)

Provides utility functions for connecting to Snowflake via the Spark
Snowflake connector and executing arbitrary SQL queries. The SQL query
comes from the pipeline config YAML at runtime.
"""

def setup_proxy(proxy_config, logger):
    """Set proxy environment variables from the connection proxy config."""
    # Sets http_proxy, https_proxy, HTTP_PROXY, HTTPS_PROXY

def get_oauth_token(account, logger):
    """Retrieve OAuth token from AWS Secrets Manager (adp/snowflake/{account}/oauth)."""

def build_sf_options(connection, oauth_token):
    """Build Snowflake Spark connector options dict."""

def run_query(spark, sf_options, query_sql, connection, logger):
    """
    Execute an arbitrary SQL query against Snowflake and return a Spark DataFrame.
    Validates SQL for safety (SELECT/WITH start check + DML/DDL blocklist).
    """
    # Defense-in-depth: validates query starts with SELECT/WITH, no DML/DDL
    # Executes via spark.read.format("net.snowflake.spark.snowflake")
```

#### Template: `templates/pyspark/iceberg_writer_spark.py`

```python
def write_to_iceberg(df, target_config, logger):
    """
    Writes a DataFrame to an Iceberg table via Glue Catalog.

    Args:
        df: PySpark DataFrame to write
        target_config: dict with target table details
        logger: Logger instance
    """
    catalog = target_config["catalog"]
    database = target_config["database"]
    table = target_config["table"]
    write_mode = target_config["write_mode"]  # "append" or "overwrite"

    table_identifier = f"{catalog}.{database}.{table}"

    logger.info(f"Writing to Iceberg table: {table_identifier} (mode={write_mode})")

    writer = df.writeTo(table_identifier)

    if write_mode == "overwrite":
        writer.overwritePartitions()
    elif write_mode == "append":
        writer.append()
    else:
        raise ValueError(f"Unsupported write_mode: {write_mode}")

    logger.info(f"Successfully wrote to {table_identifier}")
```

#### Template: `templates/common/reconciliation.py`

```python
def run_reconciliation(spark, recon_config, source_dfs, target_table, logger):
    """
    Runs reconciliation checks comparing source data against target Iceberg table.

    Args:
        spark: SparkSession
        recon_config: dict with reconciliation rules
        source_dfs: dict of source DataFrames keyed by name
        target_table: fully-qualified Iceberg table identifier
        logger: Logger instance

    Returns:
        dict with overall_status and per-rule results
    """
    results = []
    overall_status = "PASS"

    target_df = spark.table(target_table)

    for rule in recon_config["rules"]:
        rule_name = rule["name"]
        rule_type = rule["type"]
        tolerance = rule["tolerance_pct"]

        logger.info(f"Running reconciliation rule: {rule_name} (type={rule_type})")

        try:
            if rule_type == "row_count":
                source_count = spark.sql(rule["source_expr"]).collect()[0][0]
                target_count = spark.sql(rule["target_expr"]).collect()[0][0]
                diff_pct = abs(source_count - target_count) / max(source_count, 1) * 100
                passed = diff_pct <= tolerance
                result = {
                    "rule": rule_name,
                    "type": rule_type,
                    "source_value": source_count,
                    "target_value": target_count,
                    "diff_pct": round(diff_pct, 4),
                    "tolerance_pct": tolerance,
                    "status": "PASS" if passed else "FAIL",
                }

            elif rule_type == "sum":
                source_sum = spark.sql(rule["source_expr"]).collect()[0][0]
                target_sum = spark.sql(rule["target_expr"]).collect()[0][0]
                diff_pct = abs(source_sum - target_sum) / max(abs(source_sum), 1) * 100
                passed = diff_pct <= tolerance
                result = {
                    "rule": rule_name,
                    "type": rule_type,
                    "source_value": float(source_sum),
                    "target_value": float(target_sum),
                    "diff_pct": round(diff_pct, 4),
                    "tolerance_pct": tolerance,
                    "status": "PASS" if passed else "FAIL",
                }

            elif rule_type == "null_check":
                null_count = spark.sql(rule["target_expr"]).collect()[0][0]
                passed = null_count == 0
                result = {
                    "rule": rule_name,
                    "type": rule_type,
                    "null_count": null_count,
                    "status": "PASS" if passed else "FAIL",
                }

            elif rule_type == "distinct_count":
                source_val = spark.sql(rule["source_expr"]).collect()[0][0]
                target_val = spark.sql(rule["target_expr"]).collect()[0][0]
                diff_pct = abs(source_val - target_val) / max(source_val, 1) * 100
                passed = diff_pct <= tolerance
                result = {
                    "rule": rule_name,
                    "type": rule_type,
                    "source_value": source_val,
                    "target_value": target_val,
                    "diff_pct": round(diff_pct, 4),
                    "tolerance_pct": tolerance,
                    "status": "PASS" if passed else "FAIL",
                }

            else:
                result = {
                    "rule": rule_name,
                    "type": rule_type,
                    "status": "SKIP",
                    "message": f"Unknown rule type: {rule_type}",
                }
                passed = True

            if not passed:
                overall_status = "FAIL"

            results.append(result)
            logger.info(f"Rule {rule_name}: {result['status']}")

        except Exception as e:
            logger.error(f"Rule {rule_name} failed with error: {str(e)}")
            results.append({
                "rule": rule_name,
                "type": rule_type,
                "status": "ERROR",
                "message": str(e),
            })
            overall_status = "FAIL"

    return {
        "overall_status": overall_status,
        "run_timestamp": str(datetime.utcnow()),
        "correlation_id": correlation_id,
        "rules": results,
    }
```

### 5.2 How Claude Generates PySpark Glue Jobs

Given the config in Section 4.2, the Pipeline Generator Agent produces the following
complete Glue job. This shows the actual generated output, not a template.

```python
"""
Glue Job: adp-sales_analytics-monthly_revenue_by_category-etl-prod
Product: monthly_revenue_by_category
Domain: sales_analytics
Generated by AI SDLC Pipeline Generator
Version: 1.0.0
"""
import sys
import logging
import uuid
import json
from datetime import datetime

from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext
from pyspark.sql import SparkSession
import pyspark.sql.functions as F

# ── Logging Setup ────────────────────────────────────────────────────
correlation_id = str(uuid.uuid4())
logger = logging.getLogger("monthly_revenue_by_category_etl")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    f"%(asctime)s | %(levelname)s | {correlation_id} | %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)

# ── Glue / Spark Init ───────────────────────────────────────────────
args = getResolvedOptions(sys.argv, ["JOB_NAME", "ENV"])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

env = args["ENV"]
logger.info(f"Starting job {args['JOB_NAME']} in environment {env}")
logger.info(f"Correlation ID: {correlation_id}")

try:
    # ── Source: customer_orders ───────────────────────────────────
    import os
    import boto3

    os.environ["http_proxy"] = "http://corporate-proxy.company.com:8080"
    os.environ["https_proxy"] = "http://corporate-proxy.company.com:8080"
    os.environ["HTTP_PROXY"] = "http://corporate-proxy.company.com:8080"
    os.environ["HTTPS_PROXY"] = "http://corporate-proxy.company.com:8080"

    secrets_client = boto3.client("secretsmanager")
    secret_value = secrets_client.get_secret_value(
        SecretId="adp/snowflake/company-prod.us-east-1/oauth"
    )
    oauth_token = json.loads(secret_value["SecretString"])["access_token"]

    sf_options_base = {
        "sfURL": "company-prod.us-east-1.snowflakecomputing.com",
        "sfWarehouse": "ANALYTICS_WH",
        "sfRole": "ADP_READER_ROLE",
        "authenticator": "oauth",
        "token": oauth_token,
        "use_proxy": "true",
        "proxy_host": "corporate-proxy.company.com",
        "proxy_port": "8080",
    }

    logger.info("Reading source: customer_orders")
    df_customer_orders = (
        spark.read
        .format("net.snowflake.spark.snowflake")
        .options(**{
            **sf_options_base,
            "sfDatabase": "PROD_DB",
            "sfSchema": "SALES",
            "query": """
                SELECT order_id, customer_id, product_id, order_date,
                       quantity, unit_price, total_amount, order_status
                FROM PROD_DB.SALES.CUSTOMER_ORDERS
                WHERE order_status = 'COMPLETED'
                  AND order_date >= DATEADD(month, -13, CURRENT_DATE())
            """,
        })
        .load()
    )
    logger.info(f"customer_orders: {df_customer_orders.count()} rows")

    # ── Source: product_catalog ───────────────────────────────────
    logger.info("Reading source: product_catalog")
    df_product_catalog = (
        spark.read
        .format("net.snowflake.spark.snowflake")
        .options(**{
            **sf_options_base,
            "sfDatabase": "PROD_DB",
            "sfSchema": "PRODUCTS",
            "query": """
                SELECT product_id, product_name, category, subcategory, brand
                FROM PROD_DB.PRODUCTS.PRODUCT_CATALOG
            """,
        })
        .load()
    )
    logger.info(f"product_catalog: {df_product_catalog.count()} rows")

    # ── Join: customer_orders INNER JOIN product_catalog ─────────
    logger.info("Joining customer_orders with product_catalog on product_id")
    df_joined = df_customer_orders.join(
        df_product_catalog,
        df_customer_orders["product_id"] == df_product_catalog["product_id"],
        "inner"
    ).drop(df_product_catalog["product_id"])

    # ── Aggregation ──────────────────────────────────────────────
    logger.info("Aggregating monthly revenue by product category")
    df_aggregated = (
        df_joined
        .withColumn("revenue_month", F.date_trunc("month", F.col("order_date")))
        .groupBy(
            F.col("category").alias("product_category"),
            F.col("revenue_month")
        )
        .agg(
            F.sum("total_amount").alias("total_revenue"),
            F.countDistinct("order_id").alias("order_count"),
            F.avg("total_amount").alias("avg_order_value"),
            F.sum("quantity").alias("total_units_sold"),
        )
    )

    # ── Post-Aggregation Filter ──────────────────────────────────
    df_result = df_aggregated.filter(F.col("total_revenue") > 0)

    # ── Write to Iceberg ─────────────────────────────────────────
    target_table = "glue_catalog.sales_analytics_monthly_revenue_prod.monthly_revenue_by_category"
    logger.info(f"Writing to Iceberg table: {target_table}")

    df_result.writeTo(target_table).overwritePartitions()

    logger.info("Write complete.")

    # ── Reconciliation ───────────────────────────────────────────
    logger.info("Running reconciliation checks")

    # Check 1: total_revenue_check
    source_total = (
        spark.read
        .format("net.snowflake.spark.snowflake")
        .options(**{
            **sf_options_base,
            "sfDatabase": "PROD_DB",
            "sfSchema": "SALES",
            "query": """
                SELECT SUM(total_amount)
                FROM PROD_DB.SALES.CUSTOMER_ORDERS
                WHERE order_status = 'COMPLETED'
                AND order_date >= DATEADD(month, -13, CURRENT_DATE())
            """,
        })
        .load()
        .collect()[0][0]
    )

    target_total = spark.sql(
        f"SELECT SUM(total_revenue) FROM {target_table}"
    ).collect()[0][0]

    diff_pct = abs(float(source_total) - float(target_total)) / max(float(source_total), 1) * 100
    if diff_pct > 0.01:
        logger.error(f"RECON FAIL: total_revenue_check diff={diff_pct:.4f}% (tolerance=0.01%)")
        raise ValueError(f"Reconciliation failed: total_revenue_check diff={diff_pct:.4f}%")
    else:
        logger.info(f"RECON PASS: total_revenue_check diff={diff_pct:.4f}%")

    logger.info("All reconciliation checks passed.")
    logger.info("Job completed successfully.")
    job.commit()

except Exception as e:
    logger.error(f"Job failed: {str(e)}", exc_info=True)
    raise
```

### 5.3 Step Function Generation

The Pipeline Generator produces the following ASL definition:

```json
{
  "Comment": "Orchestrator for monthly_revenue_by_category analytical data product",
  "StartAt": "RunGlueJob",
  "States": {
    "RunGlueJob": {
      "Type": "Task",
      "Resource": "arn:aws:states:::glue:startJobRun.sync",
      "Parameters": {
        "JobName": "adp-sales_analytics-monthly_revenue_by_category-etl-prod",
        "Arguments": {
          "--ENV": "prod",
          "--JOB_NAME": "adp-sales_analytics-monthly_revenue_by_category-etl-prod"
        }
      },
      "Retry": [
        {
          "ErrorEquals": ["Glue.ConcurrentRunsExceededException"],
          "IntervalSeconds": 60,
          "MaxAttempts": 3,
          "BackoffRate": 2.0
        },
        {
          "ErrorEquals": ["States.TaskFailed"],
          "IntervalSeconds": 30,
          "MaxAttempts": 2,
          "BackoffRate": 2.0
        }
      ],
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "Next": "HandleError"
        }
      ],
      "Next": "RunReconciliation"
    },
    "RunReconciliation": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:::function:adp-monthly_revenue_by_category-recon-prod",
      "Retry": [
        {
          "ErrorEquals": ["Lambda.ServiceException"],
          "IntervalSeconds": 5,
          "MaxAttempts": 2,
          "BackoffRate": 2.0
        }
      ],
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "Next": "HandleError"
        }
      ],
      "Next": "CheckReconResult"
    },
    "CheckReconResult": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.overall_status",
          "StringEquals": "PASS",
          "Next": "NotifySuccess"
        }
      ],
      "Default": "NotifyFailure"
    },
    "NotifySuccess": {
      "Type": "Task",
      "Resource": "arn:aws:states:::sns:publish",
      "Parameters": {
        "TopicArn": "arn:aws:sns:us-east-1:123456789012:adp-notifications-prod",
        "Subject": "ADP Success: monthly_revenue_by_category",
        "Message.$": "States.Format('Pipeline completed successfully. Reconciliation: {}', $.overall_status)"
      },
      "End": true
    },
    "NotifyFailure": {
      "Type": "Task",
      "Resource": "arn:aws:states:::sns:publish",
      "Parameters": {
        "TopicArn": "arn:aws:sns:us-east-1:123456789012:adp-notifications-prod",
        "Subject": "ADP FAILURE: monthly_revenue_by_category",
        "Message.$": "States.Format('Pipeline reconciliation FAILED. Details: {}', $.rules)"
      },
      "Next": "MarkFailed"
    },
    "MarkFailed": {
      "Type": "Fail",
      "Cause": "Reconciliation check failed",
      "Error": "ReconFailure"
    },
    "HandleError": {
      "Type": "Task",
      "Resource": "arn:aws:states:::sns:publish",
      "Parameters": {
        "TopicArn": "arn:aws:sns:us-east-1:123456789012:adp-notifications-prod",
        "Subject": "ADP ERROR: monthly_revenue_by_category",
        "Message.$": "States.Format('Pipeline execution error: {}', $.Error)"
      },
      "Next": "MarkError"
    },
    "MarkError": {
      "Type": "Fail",
      "Cause": "Pipeline execution error",
      "Error": "ExecutionError"
    }
  }
}
```

### 5.4 Lambda Function Generation

The Pipeline Generator also creates Lambda functions for supporting tasks.

#### Reconciliation Lambda (`pipelines/monthly_revenue_by_category/lambdas/recon_checker.py`)

```python
import json
import logging
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    """
    Checks the reconciliation results written by the Glue job
    to the S3 artifacts path and returns the status.
    """
    s3 = boto3.client("s3")
    product_name = "monthly_revenue_by_category"
    env = event.get("env", "prod")
    bucket = f"sales-adp-{env}"
    key = f"sales_analytics/{product_name}/_recon/latest_result.json"

    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        result = json.loads(response["Body"].read().decode("utf-8"))
        logger.info(f"Reconciliation result: {result['overall_status']}")
        return result
    except s3.exceptions.NoSuchKey:
        logger.error("Reconciliation result file not found.")
        return {"overall_status": "FAIL", "message": "Recon result file missing."}
    except Exception as e:
        logger.error(f"Error reading recon result: {str(e)}")
        return {"overall_status": "ERROR", "message": str(e)}
```

---

## 6. CI/CD Integration

### 6.1 Pipeline Flow

```
Developer / AI Agent
     |
     | git push (generated code)
     v
+-------------------+        +-------------------+        +-------------------+
|    JENKINS        |  --->  |     JULES         |  --->  |    HARNESS        |
| (Build & Test)    |        | (AI Code Review)  |        | (Deploy)          |
+-------------------+        +-------------------+        +-------------------+
     |                            |                            |
     | - Lint (flake8)            | - Review PySpark code      | - Deploy to DEV
     | - Unit tests (pytest)      | - Check Snowflake read-    | - Run integration tests
     | - Config validation        |   only compliance          | - Deploy to STAGING
     | - Security scan (bandit)   | - Validate Terraform       | - Run recon checks
     | - Package artifacts        |   best practices           | - Deploy to PROD
     | - Terraform validate       | - Approve / Request        |   (manual gate)
     |                            |   changes                  |
     v                            v                            v
  S3 Artifact Bucket         PR Approved/Rejected        Running Pipeline
```

### 6.2 Jenkinsfile

```groovy
pipeline {
    agent { label 'glue-builder' }

    parameters {
        string(name: 'PRODUCT_NAME', description: 'Analytical Data Product name')
        choice(name: 'ENV', choices: ['dev', 'staging', 'prod'], description: 'Target environment')
    }

    environment {
        AWS_REGION        = 'us-east-1'
        ARTIFACT_BUCKET   = "sales-adp-${params.ENV}"
        PRODUCT_NAME      = "${params.PRODUCT_NAME}"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Validate Config') {
            steps {
                sh """
                    python -m pip install pyyaml jsonschema
                    python scripts/validate_config.py \
                        configs/${PRODUCT_NAME}.yaml \
                        schemas/pipeline_config_schema.json
                """
            }
        }

        stage('Lint') {
            steps {
                sh """
                    python -m pip install flake8 bandit
                    flake8 pipelines/${PRODUCT_NAME}/ --max-line-length=120
                    bandit -r pipelines/${PRODUCT_NAME}/ -ll
                """
            }
        }

        stage('Unit Test') {
            steps {
                sh """
                    python -m pip install pytest pyspark
                    pytest tests/${PRODUCT_NAME}/ -v --junitxml=test-results.xml
                """
            }
            post {
                always {
                    junit 'test-results.xml'
                }
            }
        }

        stage('Terraform Validate') {
            steps {
                dir("terraform/environments/${params.ENV}") {
                    sh """
                        terraform init -backend-config=backend-${params.ENV}.hcl -reconfigure
                        terraform validate
                        terraform fmt -check -recursive
                    """
                }
            }
        }

        stage('Package Artifacts') {
            steps {
                sh """
                    mkdir -p dist/
                    cp pipelines/${PRODUCT_NAME}/glue_jobs/*.py dist/
                    cp pipelines/${PRODUCT_NAME}/step_functions/*.json dist/
                    cp pipelines/${PRODUCT_NAME}/lambdas/*.py dist/
                    cp configs/${PRODUCT_NAME}.yaml dist/

                    aws s3 sync dist/ \
                        s3://${ARTIFACT_BUCKET}/artifacts/${PRODUCT_NAME}/${BUILD_NUMBER}/
                """
            }
        }

        stage('Terraform Plan') {
            steps {
                dir("terraform/environments/${params.ENV}") {
                    sh """
                        terraform plan \
                            -var="product_name=${PRODUCT_NAME}" \
                            -var="artifact_build=${BUILD_NUMBER}" \
                            -out=tfplan
                    """
                }
            }
        }
    }

    post {
        success {
            echo "Build ${BUILD_NUMBER} succeeded for ${PRODUCT_NAME}"
        }
        failure {
            echo "Build ${BUILD_NUMBER} FAILED for ${PRODUCT_NAME}"
        }
    }
}
```

### 6.3 Harness Deployment Pipeline

Harness handles multi-environment promotion with gates.

```yaml
# harness/pipeline.yaml (conceptual -- Harness uses its own pipeline YAML format)

pipeline:
  name: "ADP Deploy - ${product_name}"
  identifier: "adp_deploy_${product_name}"
  stages:

    - stage:
        name: "Deploy to DEV"
        type: Deployment
        spec:
          environment: dev
          steps:
            - step:
                name: Terraform Apply (DEV)
                type: TerraformApply
                spec:
                  workspace: "terraform/environments/dev"
                  plan_file: tfplan
            - step:
                name: Upload Glue Scripts
                type: ShellScript
                spec:
                  script: |
                    aws s3 cp dist/*.py s3://sales-adp-dev/scripts/${product_name}/
            - step:
                name: Trigger Test Run
                type: ShellScript
                spec:
                  script: |
                    aws stepfunctions start-execution \
                      --state-machine-arn arn:aws:states:us-east-1:111111111111:stateMachine:adp-sales_analytics-${product_name}-dev \
                      --input '{}'
            - step:
                name: Integration Test
                type: ShellScript
                spec:
                  script: |
                    python scripts/wait_for_execution.py --product ${product_name} --env dev --timeout 600
                  timeout: 15m

    - stage:
        name: "Deploy to STAGING"
        type: Deployment
        spec:
          environment: staging
          gate:
            type: Approval
            approvers: ["lead-engineer@company.com"]
            timeout: 24h
          steps:
            - step:
                name: Terraform Apply (STAGING)
                type: TerraformApply
                spec:
                  workspace: "terraform/environments/staging"
            - step:
                name: Run Reconciliation
                type: ShellScript
                spec:
                  script: |
                    python scripts/run_recon.py --product ${product_name} --env staging

    - stage:
        name: "Deploy to PROD"
        type: Deployment
        spec:
          environment: prod
          gate:
            type: Approval
            approvers: ["data-platform-lead@company.com", "product-owner@company.com"]
            timeout: 48h
          steps:
            - step:
                name: Terraform Apply (PROD)
                type: TerraformApply
                spec:
                  workspace: "terraform/environments/prod"
            - step:
                name: Smoke Test
                type: ShellScript
                spec:
                  script: |
                    python scripts/smoke_test.py --product ${product_name} --env prod
```

### 6.4 Jules Integration

Jules (AI-assisted code review) is invoked as a Jenkins post-build step or a GitHub/Bitbucket
PR check. It reviews the generated code with these focus areas:

- **Snowflake compliance:** Verify no write operations target Snowflake
- **Proxy compliance:** Ensure all Snowflake connections set `http_proxy`/`https_proxy`
- **Iceberg best practices:** Partition strategy, write mode, table properties
- **Terraform safety:** No hardcoded secrets, proper tagging, least-privilege IAM
- **PySpark quality:** Proper error handling, logging, no `collect()` on large datasets

### 6.5 Validation Gates Summary

| Gate | Stage | Blocking | Tool |
|------|-------|----------|------|
| Config schema validation | Build | Yes | Jenkins |
| Code lint (flake8) | Build | Yes | Jenkins |
| Security scan (bandit) | Build | Yes | Jenkins |
| Unit tests (pytest) | Build | Yes | Jenkins |
| Terraform validate | Build | Yes | Jenkins |
| AI code review | Post-Build | Yes (configurable) | Jules |
| Terraform plan (no destroys) | Pre-Deploy | Yes | Hook |
| Integration test | DEV | Yes | Harness |
| Reconciliation check | STAGING | Yes | Harness |
| Manual approval | STAGING->PROD | Yes | Harness |
| Smoke test | PROD | No (alerting) | Harness |

---

## 7. Terraform / Infra Provisioning

### 7.1 Infrastructure Generated per Data Product

Each analytical data product generates Terraform resources based on the selected compute engine.

**Common resources (all engines):**

| Resource | Purpose |
|----------|---------|
| `aws_glue_catalog_database` | Database in Glue Catalog for the Iceberg table |
| `aws_glue_catalog_table` | Iceberg table definition |
| `aws_iam_role` + `aws_iam_policy` | Execution role with S3, Secrets Manager, Glue Catalog access |
| `aws_sfn_state_machine` | Step Function orchestrator |
| `aws_lambda_function` (x2) | Reconciliation checker + notification handler |
| `aws_lambda_permission` | Allow Step Function to invoke Lambdas |
| `aws_cloudwatch_log_group` | Logs for compute engine, Lambda, Step Function |
| `aws_cloudwatch_metric_alarm` | Alert on job failure, duration SLA breach |
| `aws_sns_topic` + `aws_sns_topic_subscription` | Notifications for success/failure |
| `aws_scheduler_schedule` | EventBridge Scheduler for cron triggers |
| `aws_s3_object` | Upload scripts/code to S3 |

**Engine-specific resources:**

| Engine | Additional Resources |
|--------|---------------------|
| **Glue** | `aws_glue_job` (PySpark ETL job) |
| **EMR** | `aws_emrserverless_application` + `aws_emrserverless_job_run` (Serverless), or `aws_emr_cluster` + `aws_emr_instance_group` (EC2 mode) |
| **Lambda** | `aws_lambda_function` (primary ETL -- additional to recon Lambda), `aws_lambda_layer_version` (pandas, pyiceberg, snowflake-connector layers) |
| **ECS** | `aws_ecs_task_definition`, `aws_ecs_service`, `aws_ecr_repository`, `aws_ecr_lifecycle_policy` |

### 7.2 Module Structure

```
terraform/
  modules/
    glue_job/
      main.tf           # aws_glue_job, aws_glue_catalog_database, aws_glue_catalog_table
      variables.tf
      outputs.tf
    emr_cluster/
      main.tf           # aws_emrserverless_application (serverless) or aws_emr_cluster (ec2)
      variables.tf
      outputs.tf
    ecs_task/
      main.tf           # aws_ecs_task_definition, aws_ecs_service
      variables.tf
      outputs.tf
    ecr/
      main.tf           # aws_ecr_repository, aws_ecr_lifecycle_policy
      variables.tf
      outputs.tf
    step_function/
      main.tf           # aws_sfn_state_machine, aws_scheduler_schedule
      variables.tf
      outputs.tf
    lambda/
      main.tf           # aws_lambda_function, aws_lambda_permission, aws_lambda_layer_version
      variables.tf
      outputs.tf
    iam/
      main.tf           # aws_iam_role, aws_iam_policy, aws_iam_role_policy_attachment
      variables.tf
      outputs.tf
    monitoring/
      main.tf           # aws_cloudwatch_log_group, aws_cloudwatch_metric_alarm, aws_sns_topic
      variables.tf
      outputs.tf
  environments/
    dev/
      main.tf           # Module invocations with dev-specific variables
      variables.tf
      terraform.tfvars
      backend-dev.hcl
    staging/
      main.tf
      variables.tf
      terraform.tfvars
      backend-staging.hcl
    prod/
      main.tf
      variables.tf
      terraform.tfvars
      backend-prod.hcl
```

### 7.3 Platform vs Product-Level Infrastructure

| Layer | Managed By | Examples | Frequency |
|-------|-----------|----------|-----------|
| **Platform** | Platform Team (shared) | VPC, S3 buckets, Glue connections, IAM boundaries, proxy configs, Secrets Manager secrets (OAuth tokens) | Rarely changes |
| **Product** | AI SDLC (per data product) | Glue jobs, Step Functions, Lambdas, Iceberg tables, CloudWatch alarms, SNS topics, EventBridge schedules | Every product deploy |

The AI SDLC system generates ONLY product-level Terraform. Platform infrastructure is
referenced via Terraform data sources and SSM Parameter Store lookups.

### 7.4 Example Terraform Module: Glue Job

```hcl
# terraform/modules/glue_job/main.tf

resource "aws_glue_catalog_database" "product_db" {
  name        = var.glue_database_name
  description = "Database for ${var.product_name} analytical data product"

  create_table_default_permission {
    permissions = ["ALL"]
    principal {
      data_lake_principal_identifier = "IAM_ALLOWED_PRINCIPALS"
    }
  }
}

resource "aws_glue_catalog_table" "iceberg_table" {
  database_name = aws_glue_catalog_database.product_db.name
  name          = var.table_name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "table_type"           = "ICEBERG"
    "metadata_location"    = "${var.s3_path}metadata/"
    "format-version"       = "2"
  }

  open_table_format_input {
    iceberg_input {
      metadata_operation = "CREATE"
      version            = "2"
    }
  }
}

resource "aws_glue_job" "etl_job" {
  name              = var.job_name
  role_arn          = var.glue_role_arn
  glue_version      = var.glue_version
  worker_type       = var.worker_type
  number_of_workers = var.num_workers
  timeout           = var.timeout_minutes
  max_retries       = 1

  command {
    name            = "glueetl"
    script_location = "s3://${var.artifact_bucket}/scripts/${var.product_name}/${var.job_script_name}"
    python_version  = "3"
  }

  default_arguments = merge(
    {
      "--job-language"                     = "python"
      "--enable-continuous-cloudwatch-log" = "true"
      "--enable-metrics"                   = "true"
      "--enable-spark-ui"                  = "true"
      "--spark-event-logs-path"            = "s3://${var.artifact_bucket}/spark-logs/${var.product_name}/"
      "--ENV"                              = var.environment
      "--extra-py-files"                   = join(",", var.extra_py_files)
      "--extra-jars"                       = join(",", var.extra_jars)
      "--conf"                             = "spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog"
    },
    var.additional_job_parameters
  )

  tags = var.tags
}

output "job_name" {
  value = aws_glue_job.etl_job.name
}

output "database_name" {
  value = aws_glue_catalog_database.product_db.name
}
```

### 7.5 Example Terraform Environment Main

```hcl
# terraform/environments/prod/main.tf

terraform {
  required_version = ">= 1.5.0"

  backend "s3" {}

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      Team        = var.team
      ManagedBy   = "terraform"
      Project     = "analytical-data-product"
      Product     = var.product_name
    }
  }
}

# ── Data Sources (Platform Layer) ────────────────────────────────────
data "aws_ssm_parameter" "vpc_id" {
  name = "/platform/vpc/id"
}

data "aws_ssm_parameter" "glue_security_config" {
  name = "/platform/glue/security-configuration"
}

data "aws_ssm_parameter" "sns_alerts_topic" {
  name = "/platform/sns/alerts-topic-arn"
}

# ── IAM Module ───────────────────────────────────────────────────────
module "iam" {
  source = "../../modules/iam"

  product_name    = var.product_name
  environment     = var.environment
  s3_bucket_arn   = "arn:aws:s3:::${var.artifact_bucket}"
  s3_data_path    = var.s3_data_path
  secrets_arn     = var.snowflake_secret_arn
}

# ── Glue Job Module ─────────────────────────────────────────────────
module "glue_job" {
  source = "../../modules/glue_job"

  product_name          = var.product_name
  job_name              = "adp-${var.domain}-${var.product_name}-etl-${var.environment}"
  glue_database_name    = "${var.domain}_${var.product_name}_${var.environment}"
  table_name            = var.target_table_name
  s3_path               = var.s3_data_path
  artifact_bucket       = var.artifact_bucket
  job_script_name       = "${var.product_name}_etl.py"
  glue_role_arn         = module.iam.glue_role_arn
  glue_version          = var.glue_version
  worker_type           = var.worker_type
  num_workers           = var.num_workers
  timeout_minutes       = var.timeout_minutes
  extra_py_files        = var.extra_py_files
  extra_jars            = var.extra_jars
  environment           = var.environment
  tags                  = var.tags
}

# ── Step Function Module ────────────────────────────────────────────
module "step_function" {
  source = "../../modules/step_function"

  product_name       = var.product_name
  state_machine_name = "adp-${var.domain}-${var.product_name}-${var.environment}"
  definition_file    = "${path.module}/../../../pipelines/${var.product_name}/step_functions/${var.product_name}_orchestrator.asl.json"
  glue_job_name      = module.glue_job.job_name
  recon_lambda_arn   = module.lambda_recon.function_arn
  sns_topic_arn      = data.aws_ssm_parameter.sns_alerts_topic.value
  schedule_cron      = var.schedule_cron
  environment        = var.environment
  tags               = var.tags
}

# ── Lambda Modules ──────────────────────────────────────────────────
module "lambda_recon" {
  source = "../../modules/lambda"

  function_name = "adp-${var.product_name}-recon-${var.environment}"
  handler       = "recon_checker.handler"
  runtime       = "python3.11"
  source_dir    = "${path.module}/../../../pipelines/${var.product_name}/lambdas/"
  role_arn      = module.iam.lambda_role_arn
  environment_variables = {
    PRODUCT_NAME = var.product_name
    ENV          = var.environment
    S3_BUCKET    = var.artifact_bucket
  }
  tags = var.tags
}

# ── Monitoring Module ───────────────────────────────────────────────
module "monitoring" {
  source = "../../modules/monitoring"

  product_name        = var.product_name
  glue_job_name       = module.glue_job.job_name
  state_machine_arn   = module.step_function.state_machine_arn
  sns_topic_arn       = data.aws_ssm_parameter.sns_alerts_topic.value
  sla_timeout_minutes = var.timeout_minutes
  environment         = var.environment
  tags                = var.tags
}
```

---

## 8. Standardized Claude Project Template

### 8.1 Folder Structure

Every analytical data product repository follows this exact structure:

```
analytical-data-product-{name}/
|
|-- CLAUDE.md                          # Repo-level Claude instructions
|-- CLAUDE.local.md                    # Personal overrides (gitignored)
|-- README.md                          # Human-readable product documentation
|-- .mcp.json                          # MCP server config (Atlassian only)
|
|-- .claude/
|   |-- settings.json                  # Shared hooks & permissions (committed)
|   |-- settings.local.json            # Personal tokens & overrides (gitignored)
|   |
|   |-- skills/                        # Claude Code skills (slash commands)
|   |   |-- generate-pipeline/
|   |   |   |-- SKILL.md               # /generate-pipeline orchestrator (delegates by engine)
|   |   |-- generate-emr-pipeline/
|   |   |   |-- SKILL.md               # /generate-emr-pipeline (PySpark on EMR)
|   |   |-- generate-lambda-pipeline/
|   |   |   |-- SKILL.md               # /generate-lambda-pipeline (Python+Pandas on Lambda)
|   |   |-- generate-ecs-pipeline/
|   |   |   |-- SKILL.md               # /generate-ecs-pipeline (Python+Pandas on ECS)
|   |   |-- generate-step-function/
|   |   |   |-- SKILL.md               # /generate-step-function skill definition
|   |   |-- generate-terraform/
|   |   |   |-- SKILL.md               # /generate-terraform skill definition
|   |   |-- validate-config/
|   |   |   |-- SKILL.md               # /validate-config skill definition
|   |   |-- validate-connection/
|   |   |   |-- SKILL.md               # /validate-connection (Snowflake OAuth/proxy check)
|   |   |-- run-recon/
|   |       |-- SKILL.md               # /run-recon skill definition
|   |
|   |-- agents/                        # Subagent definitions (AGENT.md per agent)
|       |-- requirement-parser/
|       |   |-- AGENT.md               # Subagent: Jira ticket parsing
|       |-- spec-generator/
|       |   |-- AGENT.md               # Subagent: Technical spec + Confluence
|       |-- config-generator/
|       |   |-- AGENT.md               # Subagent: Config YAML production
|       |-- pipeline-generator/
|       |   |-- AGENT.md               # Subagent: Code generation orchestrator
|       |-- infra-agent/
|       |   |-- AGENT.md               # Subagent: Terraform generation + apply
|       |-- qa-agent/
|           |-- AGENT.md               # Subagent: Reconciliation + data quality
|
|-- configs/
|   |-- {product_name}.yaml            # Pipeline configuration (THE source of truth)
|   |-- defaults/
|   |   |-- sales_analytics.yaml       # Domain-level defaults
|   |   |-- finance_analytics.yaml
|
|-- schemas/
|   |-- pipeline_config_schema.json    # JSON Schema for config validation
|
|-- templates/
|   |-- common/                        # Shared across all engines
|   |   |-- reconciliation.py          # Source vs target comparison framework
|   |   |-- data_quality.py            # Data quality check framework
|   |-- pyspark/                       # Glue + EMR engines
|   |   |-- glue_job_boilerplate.py    # Glue-specific skeleton (GlueContext)
|   |   |-- emr_job_boilerplate.py     # EMR-specific skeleton (SparkSession)
|   |   |-- snowflake_reader_spark.py  # Spark Snowflake connector (OAuth + proxy)
|   |   |-- iceberg_writer_spark.py    # Spark writeTo() Iceberg API
|   |-- python/                        # Lambda + ECS engines
|       |-- lambda_handler.py          # Lambda handler skeleton
|       |-- ecs_entrypoint.py          # ECS containerized entry point
|       |-- Dockerfile                 # ECS Dockerfile (corporate base image)
|       |-- snowflake_reader_pandas.py # snowflake-connector-python + pandas
|       |-- iceberg_writer_pyiceberg.py # pyiceberg Table API
|
|-- hooks/
|   |-- pre-config-validation.sh       # Validates no Snowflake writes in config
|   |-- post-codegen-lint.sh           # Lints and security-scans generated code
|   |-- post-codegen-docker-lint.sh    # Lints Dockerfiles (ECS engine, hadolint)
|   |-- pre-deploy-terraform-plan.sh   # Terraform plan safety check
|   |-- post-deploy-recon.sh           # Post-deployment reconciliation trigger
|
|-- pipelines/
|   |-- {product_name}/
|       |-- glue_jobs/                 # Generated output (Glue engine)
|       |   |-- {product_name}_etl.py
|       |-- emr_jobs/                  # Generated output (EMR engine)
|       |   |-- {product_name}_etl.py
|       |-- lambda_jobs/               # Generated output (Lambda engine)
|       |   |-- {product_name}_etl.py
|       |   |-- requirements.txt
|       |-- ecs_jobs/                  # Generated output (ECS engine)
|       |   |-- {product_name}_etl.py
|       |   |-- Dockerfile
|       |   |-- requirements.txt
|       |-- step_functions/
|       |   |-- {product_name}_orchestrator.asl.json  # Generated Step Function
|       |-- lambdas/
|       |   |-- recon_checker.py                # Generated reconciliation Lambda
|       |   |-- notification_handler.py         # Generated notification Lambda
|       |-- recon/
|           |-- {product_name}_recon.py         # Generated reconciliation module
|
|-- terraform/
|   |-- modules/
|   |   |-- glue_job/                  # Glue engine
|   |   |   |-- main.tf
|   |   |   |-- variables.tf
|   |   |   |-- outputs.tf
|   |   |-- emr_cluster/               # EMR engine
|   |   |   |-- main.tf
|   |   |   |-- variables.tf
|   |   |   |-- outputs.tf
|   |   |-- ecs_task/                  # ECS engine
|   |   |   |-- main.tf
|   |   |   |-- variables.tf
|   |   |   |-- outputs.tf
|   |   |-- ecr/                       # ECS container registry
|   |   |   |-- main.tf
|   |   |   |-- variables.tf
|   |   |   |-- outputs.tf
|   |   |-- step_function/
|   |   |   |-- main.tf
|   |   |   |-- variables.tf
|   |   |   |-- outputs.tf
|   |   |-- lambda/
|   |   |   |-- main.tf
|   |   |   |-- variables.tf
|   |   |   |-- outputs.tf
|   |   |-- iam/
|   |   |   |-- main.tf
|   |   |   |-- variables.tf
|   |   |   |-- outputs.tf
|   |   |-- monitoring/
|   |       |-- main.tf
|   |       |-- variables.tf
|   |       |-- outputs.tf
|   |-- environments/
|       |-- dev/
|       |   |-- main.tf
|       |   |-- variables.tf
|       |   |-- terraform.tfvars
|       |   |-- backend-dev.hcl
|       |-- staging/
|       |   |-- main.tf
|       |   |-- variables.tf
|       |   |-- terraform.tfvars
|       |   |-- backend-staging.hcl
|       |-- prod/
|           |-- main.tf
|           |-- variables.tf
|           |-- terraform.tfvars
|           |-- backend-prod.hcl
|
|-- tests/
|   |-- {product_name}/
|   |   |-- test_etl.py                # Unit tests for PySpark logic
|   |   |-- test_recon.py              # Unit tests for reconciliation
|   |   |-- conftest.py                # Pytest fixtures (SparkSession, mock data)
|   |-- integration/
|       |-- test_pipeline_e2e.py        # End-to-end integration test
|
|-- scripts/
|   |-- validate_config.py             # CLI config validator
|   |-- run_recon.py                   # CLI reconciliation runner
|   |-- wait_for_execution.py          # Polls Step Function execution status
|   |-- smoke_test.py                  # Post-deploy smoke test
|
|-- examples/
|   |-- sample_config.yaml             # Example config for reference
|   |-- sample_requirements.json       # Example parsed requirements
|   |-- sample_spec.json               # Example technical spec
|
|-- Jenkinsfile                        # CI pipeline definition
|-- harness/
|   |-- pipeline.yaml                  # CD pipeline definition
|-- requirements.txt                   # Python dependencies
|-- pyproject.toml                     # Project metadata
```

### 8.2 Template Initialization Script

To bootstrap a new analytical data product from this template:

```bash
#!/bin/bash
# scripts/init_product.sh
# Usage: ./scripts/init_product.sh <product_name> <domain>

PRODUCT_NAME=$1
DOMAIN=$2

if [ -z "$PRODUCT_NAME" ] || [ -z "$DOMAIN" ]; then
  echo "Usage: $0 <product_name> <domain>"
  exit 1
fi

REPO_DIR="analytical-data-product-${PRODUCT_NAME}"

echo "Initializing analytical data product: ${PRODUCT_NAME} (domain: ${DOMAIN})"

# Create directory structure
mkdir -p "${REPO_DIR}/.claude/skills"/{generate-pipeline,generate-emr-pipeline,generate-lambda-pipeline,generate-ecs-pipeline,generate-step-function,generate-terraform,validate-config,validate-connection,run-recon}
mkdir -p "${REPO_DIR}/.claude/agents"/{requirement-parser,spec-generator,config-generator,pipeline-generator,infra-agent,qa-agent}
mkdir -p "${REPO_DIR}"/{configs/defaults,schemas}
mkdir -p "${REPO_DIR}/templates"/{common,pyspark,python}
mkdir -p "${REPO_DIR}/hooks"
mkdir -p "${REPO_DIR}/pipelines/${PRODUCT_NAME}"/{glue_jobs,emr_jobs,lambda_jobs,ecs_jobs,step_functions,lambdas,recon}
mkdir -p "${REPO_DIR}/terraform/modules"/{glue_job,emr_cluster,ecs_task,ecr,step_function,lambda,iam,monitoring}
mkdir -p "${REPO_DIR}/terraform/environments"/{dev,staging,prod}
mkdir -p "${REPO_DIR}/tests/${PRODUCT_NAME}"
mkdir -p "${REPO_DIR}/tests/integration"
mkdir -p "${REPO_DIR}/scripts"
mkdir -p "${REPO_DIR}/examples"
mkdir -p "${REPO_DIR}/harness"

# Copy template files from the shared template repo
TEMPLATE_REPO="/path/to/adp-template"

# Copy skills (each SKILL.md into its own directory)
for skill in generate-pipeline generate-emr-pipeline generate-lambda-pipeline generate-ecs-pipeline generate-step-function generate-terraform validate-config validate-connection run-recon; do
  cp "${TEMPLATE_REPO}/.claude/skills/${skill}/SKILL.md" "${REPO_DIR}/.claude/skills/${skill}/"
done

# Copy agent definitions (each agent has its own subdirectory with AGENT.md)
for agent in requirement-parser spec-generator config-generator pipeline-generator infra-agent qa-agent; do
  cp "${TEMPLATE_REPO}/.claude/agents/${agent}/AGENT.md" "${REPO_DIR}/.claude/agents/${agent}/"
done

# Copy code templates (engine-scoped directories)
cp "${TEMPLATE_REPO}/templates/common/"*.py "${REPO_DIR}/templates/common/"
cp "${TEMPLATE_REPO}/templates/pyspark/"*.py "${REPO_DIR}/templates/pyspark/"
cp "${TEMPLATE_REPO}/templates/python/"*.py "${REPO_DIR}/templates/python/"
cp "${TEMPLATE_REPO}/templates/python/Dockerfile" "${REPO_DIR}/templates/python/"

# Copy hooks and schemas
cp "${TEMPLATE_REPO}/hooks/"*.sh "${REPO_DIR}/hooks/"
cp "${TEMPLATE_REPO}/schemas/"*.json "${REPO_DIR}/schemas/"
cp "${TEMPLATE_REPO}/Jenkinsfile" "${REPO_DIR}/"
cp "${TEMPLATE_REPO}/requirements.txt" "${REPO_DIR}/"
cp "${TEMPLATE_REPO}/pyproject.toml" "${REPO_DIR}/"

# Generate .mcp.json (MCP server config -- Atlassian only)
cat > "${REPO_DIR}/.mcp.json" <<'MCPEOF'
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

# Generate shared Claude settings with hooks
cat > "${REPO_DIR}/.claude/settings.json" <<'SETTINGSEOF'
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$CLAUDE_PROJECT_DIR\"/hooks/pre-config-validation.sh",
            "timeout": 30
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
            "timeout": 60
          }
        ]
      }
    ]
  }
}
SETTINGSEOF

# Generate product-specific CLAUDE.md
cat > "${REPO_DIR}/CLAUDE.md" <<EOF
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

## MCP Servers
Only Atlassian MCP is configured (see .mcp.json). Provides both JIRA and Confluence tools.
Do NOT add any other MCP servers.
EOF

echo "Product initialized at: ${REPO_DIR}"
echo "Next steps:"
echo "  1. Set ATLASSIAN_API_TOKEN in .claude/settings.local.json"
echo "  2. Create configs/${PRODUCT_NAME}.yaml (set compute.engine: glue|emr|lambda|ecs)"
```

---

## 9. Governance & Data Mesh Alignment

### 9.1 Data Contracts

Every analytical data product publishes a data contract that downstream consumers can
depend on. The contract is derived from the pipeline config and published to the Glue
Catalog and Confluence.

#### Data Contract Schema

```yaml
# Derived from configs/{product_name}.yaml at deploy time

data_contract:
  product: monthly_revenue_by_category
  domain: sales_analytics
  version: "1.0.0"
  owner: sales-analytics-team@company.com
  status: active

  schema:
    columns:
      - name: product_category
        type: string
        nullable: false
        description: "Product category from the product catalog"
      - name: revenue_month
        type: date
        nullable: false
        description: "First day of the revenue month (UTC)"
      - name: total_revenue
        type: decimal(18,2)
        nullable: false
        description: "Sum of order total_amount for the category-month"
      - name: order_count
        type: bigint
        nullable: false
        description: "Distinct count of orders for the category-month"
      - name: avg_order_value
        type: decimal(18,2)
        nullable: true
        description: "Average order value for the category-month"
      - name: total_units_sold
        type: bigint
        nullable: false
        description: "Sum of quantity for the category-month"

  sla:
    freshness: "daily by 08:00 UTC"
    availability: "99.5%"
    latency_minutes: 120

  quality:
    rules:
      - "total_revenue >= 0 for all rows"
      - "product_category is never null"
      - "revenue_month is never null"
      - "row count matches source-derived count within 0% tolerance"

  lineage:
    sources:
      - system: snowflake
        database: PROD_DB
        schema: SALES
        table: CUSTOMER_ORDERS
        access: read-only
      - system: snowflake
        database: PROD_DB
        schema: PRODUCTS
        table: PRODUCT_CATALOG
        access: read-only
    target:
      system: aws_iceberg
      catalog: glue_catalog
      database: sales_analytics_monthly_revenue_prod
      table: monthly_revenue_by_category
      s3_path: s3://sales-adp-prod/sales_analytics/monthly_revenue_by_category/data/

  consumers:
    - team: executive-dashboards
      use_case: "Monthly revenue reporting"
    - team: finance-analytics
      use_case: "Revenue reconciliation"
```

### 9.2 Ownership Boundaries

In the Data Mesh model, ownership is clearly delineated:

```
+───────────────────────────────────────────────────────────────────────+
|                        PLATFORM TEAM                                  |
|  Responsibilities:                                                    |
|  - AWS account vending & networking                                   |
|  - Shared S3 buckets, VPC, proxy configuration                       |
|  - Glue Catalog shared settings                                       |
|  - Snowflake OAuth token rotation (Secrets Manager)                   |
|  - External/unmanaged Iceberg tables in Snowflake (read layer)        |
|  - CI/CD platform (Jenkins, Harness infra)                            |
|  - AI SDLC template maintenance                                      |
+───────────────────────────────────────────────────────────────────────+
                               |
                               | provides
                               v
+───────────────────────────────────────────────────────────────────────+
|               ANALYTICAL DATA PRODUCT OWNER                           |
|  Responsibilities:                                                    |
|  - Define business requirements (Jira ticket)                         |
|  - Own the pipeline config YAML                                       |
|  - Own the data contract                                              |
|  - Own the Iceberg table (schema, partitioning, evolution)            |
|  - Monitor pipeline health and reconciliation                         |
|  - Respond to downstream consumer requests                            |
|  - Approve production deployments                                     |
+───────────────────────────────────────────────────────────────────────+
                               |
                               | publishes to
                               v
+───────────────────────────────────────────────────────────────────────+
|                     DOWNSTREAM CONSUMERS                              |
|  Access:                                                              |
|  - Read Iceberg table via Glue Catalog (Athena, Spark, Presto)        |
|  - Read data contract from Confluence / Glue Catalog tags             |
|  - Subscribe to SNS notifications for freshness                       |
|  - NO direct access to source Snowflake tables                        |
+───────────────────────────────────────────────────────────────────────+
```

### 9.3 Access Control

| Resource | Access Model | Enforcement |
|----------|-------------|-------------|
| Snowflake source tables | Read-only via OAuth + proxy | IAM role + Secrets Manager + Snowflake RBAC |
| S3 data lake (Iceberg data) | Per-product S3 prefix policies | IAM policies attached to product roles |
| Glue Catalog | Database-level Lake Formation permissions | Terraform-managed Lake Formation grants |
| Step Functions | Per-product execution role | IAM role with least-privilege |
| Generated code (S3 scripts) | Read for Glue, write for CI/CD | S3 bucket policy |
| Terraform state | Per-environment state bucket | S3 backend with DynamoDB locking |
| Secrets Manager | Per-product secret access | IAM policy scoped to `adp/snowflake/*` |

### 9.4 Lineage and Observability

#### Lineage Tracking

Lineage is captured at two levels:

1. **Static lineage** (from config): Derived from `query.sql` — source table references (FQN patterns),
   CTE definitions, and column mappings from the final SELECT clause. Written to Glue Catalog table
   properties and Confluence. Generated by `governance/lineage/static_lineage.py`.

2. **Runtime lineage** (from execution): Actual row counts, timestamps, correlation IDs.
   Written to CloudWatch Logs and an S3 lineage file per run.

```json
{
  "run_id": "abc-123",
  "correlation_id": "def-456",
  "product_name": "monthly_revenue_by_category",
  "timestamp": "2026-04-03T06:15:00Z",
  "source": {
    "type": "snowflake",
    "account": "company-prod.us-east-1"
  },
  "query_sql_hash": "sha256:abc123...",
  "tables_referenced": [
    {"fqn": "PROD_DB.SALES.CUSTOMER_ORDERS", "rows_read": 2450000},
    {"fqn": "PROD_DB.PRODUCTS.PRODUCT_CATALOG", "rows_read": 15000}
  ],
  "ctes": ["completed_orders", "enriched_orders"],
  "target": {
    "table": "glue_catalog.sales_analytics_monthly_revenue_prod.monthly_revenue_by_category",
    "rows_written": 780,
    "partitions_written": 13
  },
  "reconciliation": {
    "overall_status": "PASS",
    "rules_checked": 3,
    "rules_passed": 3
  },
  "duration_seconds": 342
}
```

#### Observability Stack

| Component | Tool | What It Captures |
|-----------|------|-----------------|
| Logs | CloudWatch Logs | Structured logs with correlation IDs from Glue, Lambda, Step Functions |
| Metrics | CloudWatch Metrics | Job duration, rows processed, error counts, reconciliation pass rate |
| Alarms | CloudWatch Alarms | SLA breach (job exceeds timeout), reconciliation failure, consecutive failures |
| Dashboards | CloudWatch Dashboard (Terraform-generated) | Per-product view: last run status, trend of row counts, duration, recon results |
| Lineage | S3 lineage files + Glue Catalog properties | Source-to-target data flow per run |
| Notifications | SNS + email/PagerDuty | Real-time alerts on failure |

---

## 10. Example Walkthrough

This section walks through the complete lifecycle for the data product described in the
Jira ticket: **"Create an analytical data product that joins customer_orders and
product_catalog from Snowflake, aggregates monthly revenue by product category, and writes
to an Iceberg table."**

### Stage 1: Intake

**Trigger:** User runs the AI SDLC CLI or the Requirement Parser subagent is invoked
with ticket key `SCRUM-4`.

**Action:** The Requirement Parser calls JIRA MCP:

```
MCP Call: getJiraIssue("SCRUM-4")
```

**Artifact produced:** `s3://adp-artifacts/run-20260403-001/01-requirements.json`

```json
{
  "ticket_key": "SCRUM-4",
  "product_name": "monthly_revenue_by_category",
  "domain": "sales_analytics",
  "source": {
    "type": "snowflake",
    "connection": {
      "account": "company-prod.us-east-1",
      "warehouse": "ANALYTICS_WH",
      "role": "ADP_READER_ROLE",
      "authenticator": "oauth",
      "proxy": {
        "http_proxy": "http://corporate-proxy.company.com:8080",
        "https_proxy": "http://corporate-proxy.company.com:8080"
      }
    }
  },
  "query": {
    "sql": "WITH completed_orders AS (\n  SELECT o.\"order_id\", o.\"product_id\", o.\"order_date\", o.\"quantity\", o.\"total_amount\"\n  FROM \"PROD_DB\".\"SALES\".\"CUSTOMER_ORDERS\" o\n  WHERE o.\"order_status\" = 'COMPLETED'\n    AND o.\"order_date\" >= DATEADD(month, -13, CURRENT_DATE())\n),\nenriched_orders AS (\n  SELECT co.*, p.\"category\"\n  FROM completed_orders co\n  INNER JOIN \"PROD_DB\".\"PRODUCTS\".\"PRODUCT_CATALOG\" p ON co.\"product_id\" = p.\"product_id\"\n)\nSELECT\n  eo.\"category\" AS product_category,\n  DATE_TRUNC('month', eo.\"order_date\") AS revenue_month,\n  SUM(eo.\"total_amount\") AS total_revenue,\n  COUNT(DISTINCT eo.\"order_id\") AS order_count,\n  AVG(eo.\"total_amount\") AS avg_order_value,\n  SUM(eo.\"quantity\") AS total_units_sold\nFROM enriched_orders eo\nGROUP BY eo.\"category\", DATE_TRUNC('month', eo.\"order_date\")\nHAVING SUM(eo.\"total_amount\") > 0",
    "description": "Joins customer_orders and product_catalog, aggregates monthly revenue by category"
  },
  "target": {
    "domain": "sales_analytics",
    "product_name": "monthly_revenue_by_category",
    "table_name": "monthly_revenue_by_category",
    "write_mode": "overwrite",
    "partition_by": ["revenue_month"]
  },
  "schedule": {
    "frequency": "daily",
    "cron": "0 6 * * *"
  },
  "reconciliation": {
    "rules": [
      {"name": "total_revenue_check", "type": "sum", "source_expr": "SELECT SUM(total_amount) FROM PROD_DB.SALES.CUSTOMER_ORDERS WHERE order_status = 'COMPLETED'", "target_expr": "SELECT SUM(total_revenue) FROM monthly_revenue_by_category", "tolerance_pct": 0.01}
    ]
  },
  "data_quality": {
    "expectations": ["total_revenue >= 0", "product_category IS NOT NULL"],
    "sla_minutes": 120
  },
  "assumptions": [
    "Using last 13 months of data for order_date filter",
    "Inner join assumes all orders have matching products"
  ]
}
```

### Stage 2: Spec

**Action:** The Spec Generator reads `01-requirements.json`, enriches it with metadata
catalog information, and produces the technical spec.

**MCP Calls:**
```
MCP Call: createConfluencePage("SALES", "Tech Spec: monthly_revenue_by_category v1.0.0", <wiki_body>)
MCP Call: addCommentToJiraIssue("SCRUM-4", "Technical spec published: https://confluence.company.com/x/abc123")
```

**Artifact produced:** `s3://adp-artifacts/run-20260403-001/02-spec.json`

The spec adds details like:
- Estimated row counts (customer_orders: ~2.5M rows, product_catalog: ~15K rows)
- Join strategy: broadcast product_catalog (small table)
- Target Iceberg schema with exact column types
- Glue job sizing recommendation: G.2X workers, 10 workers, 120 min timeout
- Full reconciliation rule definitions

### Stage 3: Config

**Action:** The Config Generator reads `02-spec.json` and produces the full config YAML
shown in Section 4.2 above.

**Hooks fired:**
- `pre-config-validation.sh` -- verifies no Snowflake write operations

**Skill invoked:**
- `validate-config` -- validates against JSON Schema

**Artifact produced:** `s3://adp-artifacts/run-20260403-001/03-config.yaml`

This is the exact YAML shown in Section 4.2.

### Stage 4: Code Generate

**Action:** The Pipeline Generator reads `03-config.yaml` and invokes skills to produce
all code artifacts.

**Skills invoked:**
1. `generate-pipeline` -- deploys generic shared pipeline to `pipelines/generic/glue/` (if not already deployed)
2. `generate-step-function` -- produces Step Function ASL that passes `config_s3_path` to generic Glue job via `--CONFIG_PATH`
3. Config file `configs/monthly_revenue_by_category.yaml` is the product-specific artifact

**Hooks fired:**
- `post-codegen-lint.sh` -- runs flake8 + bandit on pipeline code

**Artifacts produced:** `s3://adp-artifacts/run-20260403-001/04-code/`
```
04-code/
  pipelines/generic/glue/glue_job_boilerplate.py   # shared generic pipeline
  pipelines/generic/glue/snowflake_reader_spark.py  # shared reader
  pipelines/generic/glue/iceberg_writer_spark.py    # shared writer
  pipelines/generic/glue/reconciliation.py          # shared recon
  configs/monthly_revenue_by_category.yaml          # product-specific config
  step_functions/monthly_revenue_by_category_orchestrator.asl.json
```

The generic Glue job reads the config at runtime via `--CONFIG_PATH` and executes `query.sql`.

### Stage 5: Build (Jenkins)

**Trigger:** Developer (or AI agent) pushes generated code to Git. Jenkins picks up the
commit.

**Jenkins stages executed:**
1. Validate Config -- PASS
2. Lint (flake8) -- PASS
3. Unit Test -- PASS (3 tests: read mock, transform mock, write mock)
4. Terraform Validate -- PASS
5. Package Artifacts -- uploaded to `s3://sales-adp-dev/artifacts/monthly_revenue_by_category/42/`
6. Terraform Plan -- plan generated, 12 resources to add

**Jules review:** Jules reviews the PR and checks:
- No Snowflake write operations -- PASS
- Proxy configured for all Snowflake connections -- PASS
- Iceberg write uses `overwritePartitions()` (not `overwrite()`) -- PASS
- IAM policy is least-privilege -- PASS
- Approves the PR.

### Stage 6: Deploy (Harness)

**DEV deployment:**
1. Terraform Apply -- 12 resources created
2. Upload Glue scripts to S3
3. Trigger test run via Step Function
4. Integration test -- Step Function completes in 4 min 22 sec, reconciliation PASS

**STAGING deployment (after lead engineer approval):**
1. Terraform Apply -- 12 resources created
2. Trigger run, reconciliation PASS

**PROD deployment (after dual approval: data platform lead + product owner):**
1. Terraform Apply -- 12 resources created
2. Smoke test -- PASS

### Stage 7: Validate (QA Agent)

**Action:** After the first production run, the QA Agent executes:

1. Reconciliation checks from the config:
   - `total_revenue_check`: Source SUM = $142,567,890.45, Target SUM = $142,567,890.45, diff = 0.0000% -- **PASS**
   - `row_count_reasonableness`: Source distinct month-category combos = 780, Target rows = 780, diff = 0.0% -- **PASS**
   - `no_null_categories`: Null count = 0 -- **PASS**

2. Data quality checks:
   - `revenue_positive`: Min total_revenue = $12.50 >= 0 -- **PASS**
   - `category_not_null`: Null count = 0 -- **PASS**
   - `month_not_null`: Null count = 0 -- **PASS**
   - `order_count_positive`: Min order_count = 1 >= 1 -- **PASS**

**MCP Calls:**
```
MCP Call: addCommentToJiraIssue("SCRUM-4", "Validation PASSED. Report: s3://adp-artifacts/run-20260403-001/06-validation-report.json")
MCP Call: transitionJiraIssue("SCRUM-4", "Done")
```

**Artifact produced:** `s3://adp-artifacts/run-20260403-001/06-validation-report.json`

```json
{
  "overall_status": "PASS",
  "run_timestamp": "2026-04-03T06:18:42Z",
  "correlation_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "product_name": "monthly_revenue_by_category",
  "environment": "prod",
  "reconciliation": {
    "rules": [
      {
        "rule": "total_revenue_check",
        "type": "sum",
        "source_value": 142567890.45,
        "target_value": 142567890.45,
        "diff_pct": 0.0,
        "tolerance_pct": 0.01,
        "status": "PASS"
      },
      {
        "rule": "row_count_reasonableness",
        "type": "row_count",
        "source_value": 780,
        "target_value": 780,
        "diff_pct": 0.0,
        "tolerance_pct": 0.0,
        "status": "PASS"
      },
      {
        "rule": "no_null_categories",
        "type": "null_check",
        "null_count": 0,
        "status": "PASS"
      }
    ]
  },
  "data_quality": {
    "checks": [
      {"name": "revenue_positive", "status": "PASS"},
      {"name": "category_not_null", "status": "PASS"},
      {"name": "month_not_null", "status": "PASS"},
      {"name": "order_count_positive", "status": "PASS"}
    ]
  }
}
```

### Stage 8: Monitor (Ongoing)

The deployed pipeline now runs daily at 06:00 UTC. Monitoring is fully automated:

- **CloudWatch Dashboard** shows: last run status (green), average duration (4m 30s),
  row count trend (780 +/- 5 per day), reconciliation pass rate (100%)
- **CloudWatch Alarm** fires if: job duration exceeds 120 min, job fails 2 consecutive
  times, or reconciliation fails
- **SNS Notifications** go to: `sales-analytics-team@company.com` on failure,
  `data-platform-alerts@company.com` on SLA breach
- **Lineage file** written to `s3://sales-adp-prod/sales_analytics/monthly_revenue_by_category/_lineage/` per run

---

## Appendix A: Key Decisions and Constraints

| Decision | Rationale |
|----------|-----------|
| Config-driven (not code-first) | Enables non-developers to define products; Claude generates code from config |
| YAML over JSON for config | More human-readable, supports comments, easier to diff in PRs |
| Skills over monolithic prompts | Reusable, testable, composable; each skill does one thing well |
| Subagents over single agent | Separation of concerns; each agent can be tested and improved independently |
| Hooks for guardrails | Automated enforcement without relying on agent compliance; defense in depth |
| Snowflake read-only enforced at 3 layers | Config validation hook + code lint + Jules review |
| Iceberg overwritePartitions (not full overwrite) | Preserves data for partitions not in the current run; safer for incremental loads |
| Terraform modules (not monolith) | Reusable across products; version-controlled independently |
| JIRA + Confluence MCP only | Organizational constraint; no GitHub MCP (code interactions via CLI/Git) |

## Appendix B: Dependencies and Versions

| Component | Version | Notes |
|-----------|---------|-------|
| AWS Glue | 4.0 | Spark 3.3.0, Python 3.10 |
| Apache Iceberg | 1.4.x | Via Glue 4.0 built-in or custom JAR |
| Snowflake Spark Connector | 2.12.x | Compatible with Spark 3.3 |
| Terraform | >= 1.5.0 | AWS provider ~> 5.0 |
| Python | 3.10+ | For Glue jobs and Lambdas |
| Jenkins | 2.4xx | LTS version |
| Harness | NextGen | SaaS |
| Claude | claude-opus-4-6 or later | Via Claude Code CLI |

## Appendix C: Glossary

| Term | Definition |
|------|-----------|
| **ADP** | Analytical Data Product |
| **Data Mesh** | Decentralized data architecture where domain teams own their data products |
| **Iceberg Table** | Open table format for large analytic datasets on S3 |
| **Glue Catalog** | AWS-managed Hive Metastore compatible catalog |
| **ASL** | Amazon States Language (Step Function definition format) |
| **Reconciliation** | Comparing source and target data to ensure completeness and accuracy |
| **MCP** | Model Context Protocol (used by Claude to interact with external tools) |
| **OAuth** | Authentication protocol used for Snowflake access |
| **Proxy** | Corporate HTTP proxy required for all Snowflake network traffic |
