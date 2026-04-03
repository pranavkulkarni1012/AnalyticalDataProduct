# AI SDLC - Implementation Stories

**Epic:** AI SDLC Framework for Analytical Data Products  
**Project:** SCRUM  
**Created:** 2026-04-03  
**Source Document:** `AI_SDLC_Plan.md`

> These stories are implementation-ready. Each contains enough context for an AI agent (Claude Code) or developer to pick up and deliver independently. Stories are ordered by dependency — earlier stories unblock later ones.

---

## Phase 1: Foundation (Project Template & Config)

### Story 1: Scaffold the Standardized Project Template

**Summary:** Create the `init_product.sh` bootstrap script and the full directory structure for an analytical data product repository.

**Acceptance Criteria:**
- [ ] Script `scripts/init_product.sh` accepts `<product_name>` and `<domain>` arguments
- [ ] Creates the complete directory tree as defined in `AI_SDLC_Plan.md` Section 8.1:
  - `.claude/skills/` with subdirectories for all 9 skills
  - `.claude/agents/` with subdirectories for all 6 agents
  - `configs/`, `schemas/`, `templates/` (engine-scoped: `common/`, `pyspark/`, `python/`)
  - `hooks/`, `pipelines/{product_name}/` (with `glue_jobs/`, `emr_jobs/`, `lambda_jobs/`, `ecs_jobs/`, `step_functions/`, `lambdas/`, `recon/`)
  - `terraform/modules/` (glue_job, emr_cluster, ecs_task, ecr, step_function, lambda, iam, monitoring)
  - `terraform/environments/` (dev, staging, prod)
  - `tests/`, `scripts/`, `examples/`, `harness/`
- [ ] Generates `.mcp.json` with Atlassian-only MCP config (using `${ATLASSIAN_API_TOKEN}` env var)
- [ ] Generates `.claude/settings.json` with all 5 hooks registered (see Section 2.4):
  - `PreToolUse` → `Write|Edit` → `pre-config-validation.sh`
  - `PreToolUse` → `Bash(terraform apply*)` → `pre-deploy-terraform-plan.sh`
  - `PostToolUse` → `Write|Edit` → `post-codegen-lint.sh`, `post-codegen-docker-lint.sh`
  - `Stop` → `post-deploy-recon.sh`
- [ ] Generates a product-specific `CLAUDE.md` with domain, owner, skills list, and MCP constraint
- [ ] Script is idempotent (safe to re-run without overwriting existing files)
- [ ] `.gitignore` includes `CLAUDE.local.md`, `.claude/settings.local.json`

**Technical Context:**
- Reference: `AI_SDLC_Plan.md` Section 8.1 (folder structure) and Section 8.2 (init script)
- The init script copies template files from a shared template repo path (`/path/to/adp-template`) — this path should be configurable via env var `ADP_TEMPLATE_REPO`

---

### Story 2: Implement the Pipeline Config JSON Schema

**Summary:** Create the JSON Schema file that validates pipeline configuration YAMLs against the canonical schema.

**Acceptance Criteria:**
- [ ] File: `schemas/pipeline_config_schema.json`
- [ ] Validates all required top-level keys: `product`, `compute`, `sources`, `transformations`, `target`, `reconciliation`, `runtime`
- [ ] `product` schema: `name` (regex `^[a-z][a-z0-9_]{2,50}$`), `domain`, `owner` (email), `version` (semver), `description`, optional `tags`, optional `schedule` (frequency enum + cron)
- [ ] `compute` schema: `engine` (enum: glue, emr, lambda, ecs), optional `language` (enum: pyspark, python)
- [ ] `sources` schema: array of objects with `name`, `type` (enum: snowflake), `connection` (account, warehouse, role, authenticator=oauth, proxy with http/https), `database`, `schema`, `table`, `columns`, `filters`
- [ ] `transformations` schema: `joins` (left, right, keys, type enum), `aggregations` (group_by, metrics with function enum), `filters`, `column_mappings`, `custom_sql`
- [ ] `target` schema: `catalog`, `database`, `table`, `s3_path` (pattern `^s3://`), `format` (const: iceberg), `write_mode` (enum: append, overwrite), optional `partition_by`, `sort_order`, `table_properties`
- [ ] `reconciliation` schema: `enabled` (boolean), `rules` array (name, type enum, source_expr, target_expr, tolerance_pct 0-100)
- [ ] `data_quality` schema: `checks` array (name, type enum: not_null/unique/range/regex/custom, column, parameters)
- [ ] `runtime` schema: common fields (timeout_minutes, max_concurrent_runs, tags) + engine-specific fields:
  - Glue: glue_version, worker_type (enum), num_workers, extra_py_files, extra_jars, job_parameters
  - EMR: emr_release (pattern), emr_mode (enum: serverless/ec2), emr_application_id, instance_type, instance_count, spark_submit_parameters
  - Lambda: lambda_memory_mb (128-10240), lambda_timeout_seconds (1-900), python_runtime (enum), lambda_layers, lambda_package_type
  - ECS: ecs_cpu (enum: 256/512/1024/2048/4096), ecs_memory, container_image, ecs_task_role, ecs_cluster

**Technical Context:**
- Full schema definition: `AI_SDLC_Plan.md` Section 4.1 (lines ~1212-1427)
- Example config for validation testing: Section 4.2

---

### Story 3: Create the Example Pipeline Config

**Summary:** Create the sample pipeline configuration YAML (`monthly_revenue_by_category`) that serves as both a reference and an integration test fixture.

**Acceptance Criteria:**
- [ ] File: `configs/monthly_revenue_by_category.yaml`
- [ ] Contains complete config as defined in `AI_SDLC_Plan.md` Section 4.2
- [ ] Two Snowflake sources: `customer_orders` (PROD_DB.SALES) and `product_catalog` (PROD_DB.PRODUCTS)
- [ ] Both sources use OAuth authentication and corporate proxy
- [ ] Inner join on `product_id`, monthly aggregation with 4 metrics (sum revenue, count distinct orders, avg order value, sum quantity)
- [ ] Target: Iceberg table via Glue Catalog, overwrite mode, partitioned by `revenue_month`
- [ ] 3 reconciliation rules (total_revenue_check, row_count_reasonableness, no_null_categories)
- [ ] 4 data quality checks (revenue_positive, category_not_null, month_not_null, order_count_positive)
- [ ] Glue runtime: version 4.0, G.2X workers, 10 workers, 120 min timeout
- [ ] `compute.engine: glue`, `compute.language: pyspark`
- [ ] File: `examples/sample_config.yaml` (copy of above for reference)
- [ ] Passes validation against the JSON Schema from Story 2

**Technical Context:**
- Full example: `AI_SDLC_Plan.md` Section 4.2 (lines ~1432-1632)

---

## Phase 2: Claude Code Skills

### Story 4: Implement `/validate-config` Skill

**Summary:** Create the SKILL.md and supporting validation logic for the `/validate-config` slash command.

**Acceptance Criteria:**
- [ ] File: `.claude/skills/validate-config/SKILL.md` with YAML frontmatter:
  - `name: validate-config`
  - `description`: Validates a pipeline configuration YAML against the standard schema
  - `argument-hint: "[config-path]"`
  - `allowed-tools: Read Grep Bash`
- [ ] Skill validates all 8 required top-level keys
- [ ] Skill validates each source has required connection fields (account, warehouse, role, authenticator=oauth)
- [ ] Skill validates join types are in enum (inner, left, right, full)
- [ ] Skill validates target has s3_path starting with `s3://`
- [ ] Skill validates reconciliation has at least one rule with tolerance_pct between 0-100
- [ ] Skill validates runtime has timeout_minutes > 0
- [ ] Skill explicitly checks no Snowflake write operations exist in transformations
- [ ] Returns structured output: PASS or FAIL with list of specific errors

**Technical Context:**
- Skill definition: `AI_SDLC_Plan.md` Section 2.2, "Skill: validate-config" (lines ~278-307)
- Use `$ARGUMENTS` for the config path, fallback to `configs/` directory scan

---

### Story 5: Implement `/validate-connection` Skill

**Summary:** Create the SKILL.md for the `/validate-connection` slash command that validates Snowflake connection configuration.

**Acceptance Criteria:**
- [ ] File: `.claude/skills/validate-connection/SKILL.md` with YAML frontmatter:
  - `name: validate-connection`
  - `description`: Validates Snowflake connection configuration before pipeline generation
  - `argument-hint: "[config-path]"`
  - `allowed-tools: Read Grep Bash`
- [ ] Checks each source has `authenticator: oauth` (no password or keypair)
- [ ] Checks `http_proxy` and `https_proxy` are both set and non-empty
- [ ] Checks proxy URL matches corporate pattern (`http://corporate-proxy.company.com:*`)
- [ ] Checks account URL format is valid (`{account}.{region}` pattern)
- [ ] Checks role name follows convention (ends with `_READER_ROLE` or `_READ_ROLE`)
- [ ] Checks no write-implying role names (`_WRITER`, `_ADMIN`, `_OWNER`)
- [ ] Checks warehouse is specified and non-empty
- [ ] Checks Secrets Manager path `adp/snowflake/{account}/oauth` is referenced correctly
- [ ] Returns structured output: PASS or FAIL with list of errors

**Technical Context:**
- Skill definition: `AI_SDLC_Plan.md` Section 2.2, "Skill: validate-connection" (lines ~412-441)

---

### Story 6: Implement `/generate-pipeline` Orchestrator Skill

**Summary:** Create the SKILL.md for the `/generate-pipeline` orchestrator that reads `compute.engine` from config and delegates to the appropriate engine-specific skill.

**Acceptance Criteria:**
- [ ] File: `.claude/skills/generate-pipeline/SKILL.md` with YAML frontmatter:
  - `name: generate-pipeline`
  - `description`: Orchestrator skill that reads compute.engine from the pipeline config and delegates to the appropriate engine-specific skill
  - `argument-hint: "[config-path]"`
  - `allowed-tools: Read Grep Glob Write Bash`
- [ ] Step 1: Read pipeline config YAML from `$ARGUMENTS` or scan `configs/`
- [ ] Step 2: Invoke `/validate-config` first
- [ ] Step 3: Invoke `/validate-connection`
- [ ] Step 4: Read `compute.engine` from config
- [ ] Step 5: Delegate based on engine:
  - `glue` → Generate PySpark Glue job inline (GlueContext, job.init/commit, templates from `templates/pyspark/glue_job_boilerplate.py`, `snowflake_reader_spark.py`, `iceberg_writer_spark.py`), output to `pipelines/{product_name}/glue_jobs/`
  - `emr` → Invoke `/generate-emr-pipeline`
  - `lambda` → Invoke `/generate-lambda-pipeline`
  - `ecs` → Invoke `/generate-ecs-pipeline`
- [ ] Step 6: Invoke `/generate-step-function`
- [ ] Step 7: Add structured logging, error handling, reconciliation calls

**Technical Context:**
- Skill definition: `AI_SDLC_Plan.md` Section 2.2, "Skill: generate-pipeline" (lines ~234-276)
- Glue code generation example: Section 5.2 (lines ~1963-2153)

---

### Story 7: Implement `/generate-emr-pipeline` Skill

**Summary:** Create the SKILL.md for the `/generate-emr-pipeline` skill that generates PySpark jobs for EMR (Serverless or EC2).

**Acceptance Criteria:**
- [ ] File: `.claude/skills/generate-emr-pipeline/SKILL.md` with YAML frontmatter:
  - `name: generate-emr-pipeline`
  - `description`: Generates a PySpark job for EMR (Serverless or EC2) from a pipeline config
  - `argument-hint: "[config-path]"`
  - `allowed-tools: Read Grep Glob Write Bash`
- [ ] Uses plain `SparkSession` (NOT GlueContext) for EMR
- [ ] Uses `if __name__ == "__main__"` entry point pattern
- [ ] Uses `argparse` for argument parsing (NOT `getResolvedOptions`)
- [ ] Iceberg catalog configured via Spark conf (same catalog settings as Glue)
- [ ] Snowflake read uses same Spark connector, OAuth + proxy pattern
- [ ] Templates: `templates/pyspark/emr_job_boilerplate.py`, `snowflake_reader_spark.py` (shared), `iceberg_writer_spark.py` (shared), `common/reconciliation.py`
- [ ] Output: `pipelines/{product_name}/emr_jobs/{job_name}.py`
- [ ] Generated code includes structured logging with correlation IDs

**Technical Context:**
- Skill definition: `AI_SDLC_Plan.md` Section 2.2, "Skill: generate-emr-pipeline" (lines ~443-484)
- Key difference from Glue: No GlueContext, SparkSession directly, argparse entry, standalone .py

---

### Story 8: Implement `/generate-lambda-pipeline` Skill

**Summary:** Create the SKILL.md for the `/generate-lambda-pipeline` skill that generates Python+Pandas Lambda handlers.

**Acceptance Criteria:**
- [ ] File: `.claude/skills/generate-lambda-pipeline/SKILL.md` with YAML frontmatter:
  - `name: generate-lambda-pipeline`
  - `description`: Generates a Python+Pandas Lambda handler from a pipeline config
  - `argument-hint: "[config-path]"`
  - `allowed-tools: Read Grep Glob Write Bash`
- [ ] Uses pandas DataFrames (NOT Spark) for all transformations
- [ ] Snowflake reads via `snowflake-connector-python` (DBAPI, not Spark connector)
- [ ] Iceberg writes via `pyiceberg` library (not Spark writeTo)
- [ ] Lambda handler signature: `handler(event, context)`
- [ ] Validates dataset size is appropriate for Lambda (< 500 MB recommended) based on config metadata
- [ ] Joins via `pandas.merge()`, aggregations via `pandas.groupby().agg()`
- [ ] Generates `requirements.txt` for Lambda layer packaging (snowflake-connector-python, pandas, pyiceberg)
- [ ] Templates: `python/lambda_handler.py`, `python/snowflake_reader_pandas.py`, `python/iceberg_writer_pyiceberg.py`, `common/reconciliation.py`
- [ ] Output: `pipelines/{product_name}/lambda_jobs/{job_name}.py` + `requirements.txt`
- [ ] Structured logging via Python `logging` module

**Technical Context:**
- Skill definition: `AI_SDLC_Plan.md` Section 2.2, "Skill: generate-lambda-pipeline" (lines ~486-530)
- Lambda constraints: 15-min timeout, 10 GB memory max (Section 2.1)

---

### Story 9: Implement `/generate-ecs-pipeline` Skill

**Summary:** Create the SKILL.md for the `/generate-ecs-pipeline` skill that generates Python+Pandas ECS Fargate tasks with Dockerfile.

**Acceptance Criteria:**
- [ ] File: `.claude/skills/generate-ecs-pipeline/SKILL.md` with YAML frontmatter:
  - `name: generate-ecs-pipeline`
  - `description`: Generates a Python+Pandas ECS Fargate task from a pipeline config. Includes Dockerfile and entrypoint script.
  - `argument-hint: "[config-path]"`
  - `allowed-tools: Read Grep Glob Write Bash`
- [ ] Uses same Python+Pandas pattern as Lambda (shared `snowflake_reader_pandas.py`, `iceberg_writer_pyiceberg.py`)
- [ ] Entry point is standalone Python script (`main.py`), not Lambda handler
- [ ] Generates Dockerfile:
  - Uses corporate base image from ECR
  - Installs dependencies from `requirements.txt`
  - Copies entrypoint script
  - Sets `CMD` to run entrypoint
  - Must pass hadolint linting
- [ ] Generates `requirements.txt`
- [ ] No timeout limit (unlike Lambda)
- [ ] Templates: `python/ecs_entrypoint.py`, `python/Dockerfile`, `python/snowflake_reader_pandas.py` (shared), `python/iceberg_writer_pyiceberg.py` (shared), `common/reconciliation.py`
- [ ] Output: `pipelines/{product_name}/ecs_jobs/{job_name}.py`, `Dockerfile`, `requirements.txt`

**Technical Context:**
- Skill definition: `AI_SDLC_Plan.md` Section 2.2, "Skill: generate-ecs-pipeline" (lines ~532-582)
- ECS constraints: corporate base image, health check endpoints, hadolint (Section 2.1)

---

### Story 10: Implement `/generate-step-function` Skill

**Summary:** Create the SKILL.md for the `/generate-step-function` skill that generates AWS Step Function state machine definitions (ASL JSON).

**Acceptance Criteria:**
- [ ] File: `.claude/skills/generate-step-function/SKILL.md` with YAML frontmatter:
  - `name: generate-step-function`
  - `description`: Generates an AWS Step Function (ASL JSON) that orchestrates the pipeline
  - `argument-hint: "[config-path]"`
  - `allowed-tools: Read Grep Glob Write`
- [ ] Reads config YAML to determine compute engine
- [ ] Builds state machine with states:
  - `Start` -> `RunJob` (engine-appropriate: `glue:startJobRun.sync` for Glue, `lambda:invoke` for Lambda, `ecs:runTask.sync` for ECS, `emr-serverless:startJobRun.sync` for EMR)
  - `RunJob` -> `CheckReconciliation` (Lambda invocation)
  - `CheckReconciliation` -> Choice: PASS -> `NotifySuccess` (SNS), FAIL -> `NotifyFailure` -> `MarkFailed`
- [ ] Retry config: 2x retries with exponential backoff on each task state
- [ ] Error catchers route to global error handler on each state
- [ ] Output: `pipelines/{product_name}/step_functions/{product_name}_orchestrator.asl.json`

**Technical Context:**
- Skill definition: `AI_SDLC_Plan.md` Section 2.2, "Skill: generate-step-function" (lines ~350-380)
- Example ASL output: Section 5.3 (lines ~2160-2268)

---

### Story 11: Implement `/generate-terraform` Skill

**Summary:** Create the SKILL.md for the `/generate-terraform` skill that generates Terraform modules for infrastructure provisioning.

**Acceptance Criteria:**
- [ ] File: `.claude/skills/generate-terraform/SKILL.md` with YAML frontmatter:
  - `name: generate-terraform`
  - `description`: Generates Terraform modules for the analytical data product infrastructure
  - `argument-hint: "[config-path]"`
  - `allowed-tools: Read Grep Glob Write Bash`
- [ ] Reads config to determine engine and generates appropriate resources
- [ ] Common resources (all engines): Glue Catalog database/table, IAM roles, Step Function, recon Lambda, CloudWatch logs/alarms, SNS topic, EventBridge schedule, S3 object uploads
- [ ] Engine-specific resources:
  - Glue: `aws_glue_job`
  - EMR: `aws_emrserverless_application` (serverless) or `aws_emr_cluster` (ec2)
  - Lambda: `aws_lambda_function` (primary ETL), `aws_lambda_layer_version`
  - ECS: `aws_ecs_task_definition`, `aws_ecs_service`, `aws_ecr_repository`, `aws_ecr_lifecycle_policy`
- [ ] Module structure: `terraform/modules/{glue_job,emr_cluster,ecs_task,ecr,step_function,lambda,iam,monitoring}/` each with `main.tf`, `variables.tf`, `outputs.tf`
- [ ] Environment configs: `terraform/environments/{dev,staging,prod}/main.tf` with module invocations
- [ ] Uses `data` sources for platform-layer references (VPC, Glue security config, SNS topic via SSM)
- [ ] No hardcoded secrets, proper tagging, least-privilege IAM

**Technical Context:**
- Skill definition: `AI_SDLC_Plan.md` Section 2.2, "Skill: generate-terraform" (lines ~309-348)
- Module structure: Section 7.2 (lines ~2599-2652)
- Example Glue module: Section 7.4 (lines ~2664-2741)
- Example env main.tf: Section 7.5 (lines ~2743-2865)

---

### Story 12: Implement `/run-recon` Skill

**Summary:** Create the SKILL.md for the `/run-recon` skill that generates reconciliation checks.

**Acceptance Criteria:**
- [ ] File: `.claude/skills/run-recon/SKILL.md` with YAML frontmatter:
  - `name: run-recon`
  - `description`: Generates reconciliation SQL/PySpark checks based on the reconciliation section of the config
  - `argument-hint: "[config-path]"`
  - `allowed-tools: Read Grep Glob Write Bash`
- [ ] Reads `reconciliation.rules` from config
- [ ] For each rule, generates: source query (Snowflake read-only), target query (Iceberg via Glue Catalog), comparison expression with tolerance
- [ ] Supports rule types: `row_count`, `sum`, `distinct_count`, `null_check`
- [ ] Generates a function that runs all checks and returns structured report with `overall_status` (PASS/FAIL), `run_timestamp`, `correlation_id`, per-rule results
- [ ] Output: `pipelines/{product_name}/recon/{product_name}_recon.py`

**Technical Context:**
- Skill definition: `AI_SDLC_Plan.md` Section 2.2, "Skill: run-recon" (lines ~382-410)
- Reconciliation template code: Section 5.1, `templates/common/reconciliation.py` (lines ~1847-1961)

---

## Phase 3: Code Templates

### Story 13: Create PySpark Templates (Glue + EMR)

**Summary:** Implement the PySpark code templates shared by Glue and EMR engines.

**Acceptance Criteria:**
- [ ] `templates/pyspark/glue_job_boilerplate.py` — Glue-specific skeleton with:
  - `getResolvedOptions` for arg parsing
  - `GlueContext`, `SparkContext`, `Job` init/commit lifecycle
  - Correlation ID + structured logging setup
  - `{{ generated_code }}` placeholder
  - Try/except with logging
- [ ] `templates/pyspark/emr_job_boilerplate.py` — EMR-specific skeleton with:
  - `argparse` for arg parsing
  - Plain `SparkSession.builder` init (no GlueContext)
  - Iceberg catalog configured via Spark conf
  - `if __name__ == "__main__"` entry point
  - Correlation ID + structured logging
- [ ] `templates/pyspark/snowflake_reader_spark.py` — Shared Snowflake reader:
  - `read_from_snowflake(spark, source_config)` function
  - Sets proxy env vars (http_proxy, https_proxy, HTTP_PROXY, HTTPS_PROXY)
  - Fetches OAuth token from Secrets Manager (`adp/snowflake/{account}/oauth`)
  - Uses `net.snowflake.spark.snowflake` format with sfOptions
  - Builds query with column selection and filters
  - Logs row counts
- [ ] `templates/pyspark/iceberg_writer_spark.py` — Shared Iceberg writer:
  - `write_to_iceberg(df, target_config, logger)` function
  - Uses `df.writeTo(table_identifier)`
  - Supports `overwritePartitions()` and `append()`

**Technical Context:**
- Glue boilerplate: `AI_SDLC_Plan.md` Section 5.1 (lines ~1678-1735)
- Snowflake reader: Section 5.1 (lines ~1737-1810)
- Iceberg writer: Section 5.1 (lines ~1812-1843)
- Generated Glue job example: Section 5.2 (full working example, lines ~1963-2153)

---

### Story 14: Create Python/Pandas Templates (Lambda + ECS)

**Summary:** Implement the Python+Pandas code templates shared by Lambda and ECS engines.

**Acceptance Criteria:**
- [ ] `templates/python/lambda_handler.py` — Lambda function skeleton:
  - `handler(event, context)` function signature
  - Structured logging with correlation ID
  - Error handling with CloudWatch-friendly output
  - `{{ generated_code }}` placeholder
- [ ] `templates/python/ecs_entrypoint.py` — ECS container entry point:
  - `main()` function with `if __name__ == "__main__"` entry
  - `argparse` for CLI arguments (env, product_name)
  - Structured logging with correlation ID
  - Health check endpoint support (optional)
  - `{{ generated_code }}` placeholder
- [ ] `templates/python/Dockerfile` — ECS Dockerfile:
  - `FROM` corporate base image placeholder (ECR URI)
  - `COPY requirements.txt` + `pip install`
  - `COPY` entrypoint script
  - `HEALTHCHECK` instruction
  - `CMD ["python", "main.py"]`
  - Must pass `hadolint` linting
- [ ] `templates/python/snowflake_reader_pandas.py` — Pandas-based Snowflake reader:
  - `read_from_snowflake(source_config)` function
  - Uses `snowflake-connector-python` with `cursor.fetch_pandas_all()`
  - OAuth token from Secrets Manager
  - Proxy env vars set
  - Returns `pandas.DataFrame`
- [ ] `templates/python/iceberg_writer_pyiceberg.py` — pyiceberg-based writer:
  - `write_to_iceberg(df, target_config, logger)` function
  - Uses `pyiceberg` `Table.append()` or `Table.overwrite()` API
  - Converts pandas DataFrame to PyArrow table for writing

**Technical Context:**
- Template directory structure: `AI_SDLC_Plan.md` Section 5.1 (lines ~1640-1676)
- Lambda and ECS share `snowflake_reader_pandas.py` and `iceberg_writer_pyiceberg.py`
- Lambda skill details: Section 2.2 (lines ~486-530)
- ECS skill details: Section 2.2 (lines ~532-582)

---

### Story 15: Create Common Templates (Reconciliation + Data Quality)

**Summary:** Implement the shared reconciliation and data quality templates used by all compute engines.

**Acceptance Criteria:**
- [ ] `templates/common/reconciliation.py`:
  - `run_reconciliation(spark_or_connection, recon_config, source_dfs_or_connection, target_table, logger)` function
  - Supports 4 rule types: `row_count`, `sum`, `distinct_count`, `null_check`
  - Each rule compares source vs target with tolerance_pct
  - Returns dict: `overall_status` (PASS/FAIL), `run_timestamp`, `correlation_id`, `rules` (per-rule results with status, values, diff_pct)
  - Error handling per rule (rule failures don't stop other rules)
  - Works with both PySpark (Spark SQL) and Pandas (direct query) engines
- [ ] `templates/common/data_quality.py`:
  - `run_data_quality_checks(df_or_connection, dq_config, logger)` function
  - Supports check types: `not_null`, `unique`, `range`, `regex`, `custom`
  - Returns structured report with per-check results

**Technical Context:**
- Reconciliation template: `AI_SDLC_Plan.md` Section 5.1 (lines ~1845-1961)
- Data quality schema: Section 4.1, `data_quality` section

---

## Phase 4: Subagents

### Story 16: Implement Requirement Parser Agent

**Summary:** Create the AGENT.md for the Requirement Parser subagent that reads Jira tickets via MCP and extracts structured requirements.

**Acceptance Criteria:**
- [ ] File: `.claude/agents/requirement-parser/AGENT.md` with YAML frontmatter:
  - `name: requirement-parser`
  - `description`: Reads a Jira ticket via JIRA MCP and extracts a structured requirement object
  - `tools`: `Read Write Bash mcp__atlassian__getJiraIssue mcp__atlassian__addCommentToJiraIssue`
- [ ] Fetches ticket via `getJiraIssue`: title, description, acceptance criteria, labels, components
- [ ] Parses description to identify: source datasets, transformations (joins, filters, aggregations, column mappings), target table, data quality expectations, schedule
- [ ] Ambiguous fields go into `assumptions` list
- [ ] Output schema includes: `ticket_key`, `product_name`, `domain`, `sources[]`, `transformations{}` (joins, aggregations, filters, column_mappings), `target{}`, `schedule{}`, `data_quality{}`, `assumptions[]`
- [ ] Output written to: `s3://adp-artifacts/{run_id}/01-requirements.json`
- [ ] Retry: 3x with exponential backoff (2s, 4s, 8s) on MCP timeout
- [ ] If ticket doesn't exist → error. If description empty → error requesting manual input

**Technical Context:**
- Agent definition: `AI_SDLC_Plan.md` Section 2.3 and detailed spec in Section 3.2.1 (lines ~1090-1103)
- Full AGENT.md content: Section 2.3 (lines ~605-690)

---

### Story 17: Implement Spec Generator Agent

**Summary:** Create the AGENT.md for the Spec Generator subagent that produces technical specifications and publishes to Confluence.

**Acceptance Criteria:**
- [ ] File: `.claude/agents/spec-generator/AGENT.md` with YAML frontmatter:
  - `name: spec-generator`
  - `description`: Takes parsed requirement JSON and produces a detailed technical specification, publishing it to Confluence via MCP
  - `tools`: `Read Write Bash mcp__atlassian__createConfluencePage mcp__atlassian__updateConfluencePage mcp__atlassian__addCommentToJiraIssue`
- [ ] Input: `01-requirements.json`
- [ ] Enriches requirements with: Snowflake FQN table names, join strategy (broadcast vs shuffle), Iceberg table schema, reconciliation rules, compute engine configuration
- [ ] Resolves table metadata from S3 metadata catalog (NOT direct Snowflake query)
- [ ] Formats spec as Confluence page body
- [ ] Calls Confluence MCP to create/update page
- [ ] Calls JIRA MCP to comment on ticket with Confluence link
- [ ] Output: `s3://adp-artifacts/{run_id}/02-spec.json` + Confluence page
- [ ] Fallback: if Confluence MCP fails, write spec to local markdown

**Technical Context:**
- Agent definition: `AI_SDLC_Plan.md` Section 2.3 (lines ~692-731)
- Detailed spec: Section 3.2.2 (lines ~1105-1121)

---

### Story 18: Implement Config Generator Agent

**Summary:** Create the AGENT.md for the Config Generator subagent that produces validated pipeline config YAML from technical specs.

**Acceptance Criteria:**
- [ ] File: `.claude/agents/config-generator/AGENT.md` with YAML frontmatter:
  - `name: config-generator`
  - `description`: Takes technical spec JSON and produces a validated pipeline config YAML
  - `tools`: `Read Write Bash Glob Grep`
- [ ] Skills used: `validate-config`, `validate-connection`
- [ ] Input: `02-spec.json`
- [ ] Maps spec elements to config schema (Section 4.1)
- [ ] Applies defaults from domain default config template (`configs/defaults/{domain}.yaml`)
- [ ] Runs `/validate-config` and `/validate-connection`
- [ ] Auto-fix validation errors up to 3 retries
- [ ] If unfixable, write partial config with `status: invalid` and halt
- [ ] Output: `s3://adp-artifacts/{run_id}/03-config.yaml`

**Technical Context:**
- Detailed spec: `AI_SDLC_Plan.md` Section 3.2.3 (lines ~1123-1136)

---

### Story 19: Implement Pipeline Generator Agent

**Summary:** Create the AGENT.md for the Pipeline Generator subagent that generates ETL code from config.

**Acceptance Criteria:**
- [ ] File: `.claude/agents/pipeline-generator/AGENT.md` with YAML frontmatter:
  - `name: pipeline-generator`
  - `description`: Takes pipeline config YAML and generates all ETL code, Step Functions, and supporting Lambdas
  - `tools`: `Read Write Bash Glob Grep`
- [ ] Skills used: `generate-pipeline`, `generate-emr-pipeline`, `generate-lambda-pipeline`, `generate-ecs-pipeline`, `generate-step-function`
- [ ] Input: `03-config.yaml`
- [ ] Invokes `/generate-pipeline` (orchestrator) which delegates by engine
- [ ] Invokes `/generate-step-function` for orchestration ASL
- [ ] Generates supporting Lambda functions (recon checker, notification handler)
- [ ] Generates unit test stubs for each generated job
- [ ] Auto-fix lint failures (import ordering, trailing whitespace) and retry
- [ ] Halt on security scan failure
- [ ] Output: `s3://adp-artifacts/{run_id}/04-code/` directory

**Technical Context:**
- Detailed spec: `AI_SDLC_Plan.md` Section 3.2.4 (lines ~1138-1152)
- Pipeline Generator uses all engine-specific skills: Section 2.3 subagent table

---

### Story 20: Implement Infra Agent

**Summary:** Create the AGENT.md for the Infra Agent subagent that generates and applies Terraform.

**Acceptance Criteria:**
- [ ] File: `.claude/agents/infra-agent/AGENT.md` with YAML frontmatter:
  - `name: infra-agent`
  - `description`: Generates Terraform modules and manages infrastructure deployment
  - `tools`: `Read Write Bash Glob Grep`
- [ ] Skills used: `generate-terraform`
- [ ] Input: `03-config.yaml` + `04-code/`
- [ ] Invokes `/generate-terraform`
- [ ] Runs `terraform fmt` and `terraform validate`
- [ ] Pre-deploy hook runs `terraform plan`
- [ ] Non-production: auto-apply. Production: create PR and wait for approval
- [ ] Halt on destructive changes (requires manual approval)
- [ ] Auto-fix validation failures up to 3 retries
- [ ] Output: `s3://adp-artifacts/{run_id}/05-infra-state/`

**Technical Context:**
- Detailed spec: `AI_SDLC_Plan.md` Section 3.2.5 (lines ~1154-1167)

---

### Story 21: Implement QA Agent

**Summary:** Create the AGENT.md for the QA Agent subagent that runs reconciliation and data quality checks.

**Acceptance Criteria:**
- [ ] File: `.claude/agents/qa-agent/AGENT.md` with YAML frontmatter:
  - `name: qa-agent`
  - `description`: Runs reconciliation checks and data quality validation after pipeline execution
  - `tools`: `Read Write Bash Glob Grep mcp__atlassian__addCommentToJiraIssue mcp__atlassian__transitionJiraIssue`
- [ ] Skills used: `run-recon`, `validate-config`
- [ ] Input: `03-config.yaml` + pipeline execution results
- [ ] Invokes `/run-recon` to generate reconciliation checks
- [ ] Executes reconciliation against source (Snowflake) and target (Iceberg)
- [ ] Runs data quality checks (null rates, uniqueness, value distributions)
- [ ] Generates validation report
- [ ] Comments on Jira ticket with results
- [ ] Transitions Jira ticket: "Done" (if pass) or "Failed" (if fail)
- [ ] Within-tolerance failures: PASS with warnings. Beyond-tolerance: FAIL, halt promotion
- [ ] Output: `s3://adp-artifacts/{run_id}/06-validation-report.json`

**Technical Context:**
- Detailed spec: `AI_SDLC_Plan.md` Section 3.2.6 (lines ~1169-1183)

---

## Phase 5: Hooks & Guardrails

### Story 22: Implement All Hook Scripts

**Summary:** Create the 5 hook shell scripts that enforce guardrails at each SDLC stage.

**Acceptance Criteria:**
- [ ] All hooks follow Claude Code standard: read JSON from stdin, write errors to stderr, use exit 2 to block, exit 0 to allow
- [ ] `hooks/pre-config-validation.sh`:
  - Fires on: `PreToolUse` → `Write|Edit` (YAML files)
  - Checks for Snowflake write operations (INSERT INTO, MERGE INTO, UPDATE, DELETE FROM, CREATE TABLE)
  - Blocks with exit 2 if found
- [ ] `hooks/pre-deploy-terraform-plan.sh`:
  - Fires on: `PreToolUse` → `Bash(terraform apply*)`
  - Runs `terraform init` + `terraform plan -detailed-exitcode`
  - Blocks if plan fails or includes resource destruction
- [ ] `hooks/post-codegen-lint.sh`:
  - Fires on: `PostToolUse` → `Write|Edit` (.py files)
  - Runs `flake8` (max-line-length=120) and `bandit` (security scan)
  - Reports failures to stderr (PostToolUse hooks are advisory, cannot block)
- [ ] `hooks/post-codegen-docker-lint.sh`:
  - Fires on: `PostToolUse` → `Write|Edit` (Dockerfile)
  - Runs `hadolint` if installed
  - Graceful skip if hadolint not available
- [ ] `hooks/post-deploy-recon.sh`:
  - Fires on: `Stop` event
  - Invokes reconciliation Lambda via `aws lambda invoke`
  - Blocks if reconciliation fails

**Technical Context:**
- Full hook implementations: `AI_SDLC_Plan.md` Section 2.4 (lines ~740-901)
- Hook registration in settings.json: Section 2.4 (lines ~910-973)
- Hook blocking behavior: Section 2.4 (lines ~986-992)

---

## Phase 6: Terraform Modules

### Story 23: Implement Glue Job Terraform Module

**Summary:** Create the reusable Terraform module for Glue engine resources.

**Acceptance Criteria:**
- [ ] `terraform/modules/glue_job/main.tf`:
  - `aws_glue_catalog_database` with product naming convention
  - `aws_glue_catalog_table` with Iceberg format (table_type=ICEBERG, format-version=2)
  - `aws_glue_job` with configurable: role_arn, glue_version, worker_type, num_workers, timeout, script_location, extra_py_files, extra_jars, default_arguments (Spark configs, Iceberg catalog), tags
- [ ] `terraform/modules/glue_job/variables.tf`: all input variables with descriptions and validation rules
- [ ] `terraform/modules/glue_job/outputs.tf`: job_name, database_name

**Technical Context:**
- Example module: `AI_SDLC_Plan.md` Section 7.4 (lines ~2664-2741)

---

### Story 24: Implement EMR Cluster Terraform Module

**Summary:** Create the reusable Terraform module for EMR engine resources.

**Acceptance Criteria:**
- [ ] `terraform/modules/emr_cluster/main.tf`:
  - Support both EMR Serverless (`aws_emrserverless_application`) and EC2 (`aws_emr_cluster` + `aws_emr_instance_group`) modes
  - EMR Serverless: configurable application name, release label, auto_start/stop configs
  - EMR on EC2: master/core instance types, instance counts, EMR release
  - Security configuration, logging to S3
- [ ] `terraform/modules/emr_cluster/variables.tf`: mode (serverless/ec2), release label, instance configs, tags
- [ ] `terraform/modules/emr_cluster/outputs.tf`: application_id (serverless) or cluster_id (ec2)

**Technical Context:**
- Engine-specific resources table: `AI_SDLC_Plan.md` Section 7.1 (lines ~2590-2597)
- Module structure: Section 7.2

---

### Story 25: Implement ECS Task + ECR Terraform Modules

**Summary:** Create the reusable Terraform modules for ECS engine resources and ECR repository.

**Acceptance Criteria:**
- [ ] `terraform/modules/ecs_task/main.tf`:
  - `aws_ecs_task_definition` with Fargate launch type, configurable CPU/memory, container definition, task role, execution role
  - `aws_ecs_service` (optional, for long-running tasks)
  - CloudWatch log group for container logs
- [ ] `terraform/modules/ecs_task/variables.tf`: cpu, memory, container_image, task_role_arn, cluster_name, tags
- [ ] `terraform/modules/ecs_task/outputs.tf`: task_definition_arn, service_name
- [ ] `terraform/modules/ecr/main.tf`:
  - `aws_ecr_repository` with naming convention `adp/{domain}/{product_name}`
  - `aws_ecr_lifecycle_policy` (keep last 10 images)
  - Image scanning on push enabled
- [ ] `terraform/modules/ecr/variables.tf`: repository_name, tags
- [ ] `terraform/modules/ecr/outputs.tf`: repository_url, repository_arn

**Technical Context:**
- Engine-specific resources table: `AI_SDLC_Plan.md` Section 7.1
- Module structure: Section 7.2

---

### Story 26: Implement Common Terraform Modules (Step Function, Lambda, IAM, Monitoring)

**Summary:** Create the shared Terraform modules used by all compute engines.

**Acceptance Criteria:**
- [ ] `terraform/modules/step_function/main.tf`:
  - `aws_sfn_state_machine` with ASL definition from file
  - `aws_scheduler_schedule` for cron triggers (EventBridge Scheduler)
  - IAM role for Step Function execution
- [ ] `terraform/modules/lambda/main.tf`:
  - `aws_lambda_function` with configurable handler, runtime (python3.11), source_dir, role, env vars
  - `aws_lambda_permission` for Step Function invocation
  - Optional `aws_lambda_layer_version` for dependencies
- [ ] `terraform/modules/iam/main.tf`:
  - Execution role with: S3 access (scoped to product prefix), Secrets Manager (scoped to `adp/snowflake/*`), Glue Catalog, CloudWatch Logs
  - Separate roles for compute engine, Lambda, Step Function
  - Least-privilege policies
- [ ] `terraform/modules/monitoring/main.tf`:
  - `aws_cloudwatch_log_group` for all components
  - `aws_cloudwatch_metric_alarm` for job failure and SLA breach
  - `aws_sns_topic` + `aws_sns_topic_subscription`
- [ ] All modules have `variables.tf` and `outputs.tf`

**Technical Context:**
- Module structure: `AI_SDLC_Plan.md` Section 7.2 (lines ~2599-2652)
- Example env main.tf showing module usage: Section 7.5 (lines ~2743-2865)

---

### Story 27: Implement Terraform Environment Configurations

**Summary:** Create the per-environment `main.tf` files that wire all modules together.

**Acceptance Criteria:**
- [ ] `terraform/environments/dev/main.tf`: provider config, data sources (VPC, Glue security config, SNS topic via SSM), module invocations for all components
- [ ] `terraform/environments/staging/main.tf`: same structure, staging-specific vars
- [ ] `terraform/environments/prod/main.tf`: same structure, prod-specific vars
- [ ] Each env has: `variables.tf`, `terraform.tfvars`, `backend-{env}.hcl`
- [ ] Backend: S3 + DynamoDB locking
- [ ] Provider: AWS with `default_tags` (Environment, Team, ManagedBy=terraform, Project, Product)
- [ ] Module invocations are conditional on compute engine (e.g., only create `glue_job` module if engine=glue)

**Technical Context:**
- Example prod main.tf: `AI_SDLC_Plan.md` Section 7.5 (lines ~2743-2865)
- Platform vs product infrastructure: Section 7.3

---

## Phase 7: CI/CD Pipeline

### Story 28: Create Jenkins CI Pipeline (Jenkinsfile)

**Summary:** Implement the Jenkinsfile for build, lint, test, and artifact packaging.

**Acceptance Criteria:**
- [ ] File: `Jenkinsfile`
- [ ] Parameters: `PRODUCT_NAME` (string), `ENV` (choice: dev/staging/prod)
- [ ] Stages:
  1. Checkout
  2. Validate Config (`validate_config.py` against JSON Schema)
  3. Lint (`flake8 --max-line-length=120`, `bandit -r -ll`)
  4. Unit Test (`pytest` with JUnit XML report)
  5. Terraform Validate (`terraform init`, `terraform validate`, `terraform fmt -check`)
  6. Package Artifacts (copy to `dist/`, upload to S3)
  7. Terraform Plan (save plan file)
- [ ] Post: success/failure notifications
- [ ] Agent label: `glue-builder`
- [ ] Environment variables: `AWS_REGION`, `ARTIFACT_BUCKET`, `PRODUCT_NAME`

**Technical Context:**
- Full Jenkinsfile: `AI_SDLC_Plan.md` Section 6.2 (lines ~2339-2445)

---

### Story 29: Create Harness CD Pipeline

**Summary:** Implement the Harness deployment pipeline for multi-environment promotion with gates.

**Acceptance Criteria:**
- [ ] File: `harness/pipeline.yaml`
- [ ] 3 stages: DEV deploy, STAGING deploy (with approval gate), PROD deploy (with dual approval gate)
- [ ] DEV stage: Terraform apply, upload scripts, trigger Step Function, integration test (10 min timeout)
- [ ] STAGING stage: approval gate (lead-engineer, 24h timeout), Terraform apply, run reconciliation
- [ ] PROD stage: dual approval (data-platform-lead + product-owner, 48h timeout), Terraform apply, smoke test
- [ ] Validation report auto-posted to Jira ticket at each promotion

**Technical Context:**
- Full Harness pipeline: `AI_SDLC_Plan.md` Section 6.3 (lines ~2448-2537)
- Validation gates summary: Section 6.5

---

## Phase 8: Testing & Scripts

### Story 30: Create Utility Scripts

**Summary:** Implement the CLI utility scripts for config validation, reconciliation, execution monitoring, and smoke testing.

**Acceptance Criteria:**
- [ ] `scripts/validate_config.py`: CLI tool that validates a YAML config against the JSON Schema, returns exit code 0 (pass) or 1 (fail) with error list
- [ ] `scripts/run_recon.py`: CLI tool that runs reconciliation checks for a given product/env, outputs structured report
- [ ] `scripts/wait_for_execution.py`: Polls Step Function execution status until complete or timeout, returns exit code based on execution result
- [ ] `scripts/smoke_test.py`: Post-deploy smoke test — checks Iceberg table exists, has recent data, CloudWatch alarms in OK state

---

### Story 31: Create Unit Test Framework and Sample Tests

**Summary:** Set up pytest fixtures and create unit tests for the example monthly_revenue product.

**Acceptance Criteria:**
- [ ] `tests/conftest.py`: shared fixtures
- [ ] `tests/monthly_revenue_by_category/conftest.py`: SparkSession fixture (local mode), mock Snowflake data (sample DataFrames), mock Secrets Manager
- [ ] `tests/monthly_revenue_by_category/test_etl.py`: tests for join logic, aggregation logic, filter logic, column mappings
- [ ] `tests/monthly_revenue_by_category/test_recon.py`: tests for each reconciliation rule type (row_count, sum, null_check), tolerance handling, error cases
- [ ] `tests/integration/test_pipeline_e2e.py`: end-to-end test using local Spark + mock data, validates full pipeline from read to write to recon
- [ ] `requirements.txt` includes test dependencies: pytest, pyspark, moto (AWS mocking), pandas

---

## Phase 9: Governance & Documentation

### Story 32: Implement Data Contracts and Lineage

**Summary:** Create the data contract framework and lineage tracking mechanism.

**Acceptance Criteria:**
- [ ] Data contract template (schema definition, SLA guarantees, quality thresholds, version)
- [ ] Data contract published to Confluence via Spec Generator agent
- [ ] Static lineage: config-derived source-to-target mappings, extractable from YAML
- [ ] Runtime lineage: Spark job metadata, execution logs with correlation IDs
- [ ] Correlation IDs propagated across all pipeline stages (Glue job -> Lambda -> Step Function)
- [ ] CloudWatch dashboards template per product

**Technical Context:**
- Governance section: `AI_SDLC_Plan.md` Section 9 (lines ~3194+)
- Data contracts, lineage, ownership boundaries

---

### Story 33: Create Global CLAUDE.md

**Summary:** Create the organization-wide Global CLAUDE.md with all constraints and standards.

**Acceptance Criteria:**
- [ ] File: `~/.claude/CLAUDE.md` (or documented as such for distribution)
- [ ] Identity section: AI SDLC agent for Analytical Data Products on AWS
- [ ] Hard Constraints: Snowflake read-only, OAuth + proxy, Iceberg on S3 via Glue Catalog, Atlassian MCP only, separate AWS accounts per producer, Terraform only, Jenkins + Harness + Jules
- [ ] Supported Compute Engines section: Glue, EMR, Lambda, ECS — each with specific constraints and "best for" guidance
- [ ] Naming Conventions: S3 paths, Glue databases, Iceberg tables, Step Functions, Glue Jobs, EMR Applications, Lambda Functions, ECS Tasks, ECR Repositories
- [ ] Code Standards: structured logging, parameterized SQL (both Spark and Python), reconciliation mandatory

**Technical Context:**
- Full content: `AI_SDLC_Plan.md` Section 2.1 (lines ~109-186)

---

## Story Dependency Map

```
Phase 1 (Foundation):     Story 1 → Story 2 → Story 3
Phase 2 (Skills):         Story 4, 5 (parallel) → Story 6 → Stories 7, 8, 9 (parallel) → Stories 10, 11, 12 (parallel)
Phase 3 (Templates):      Stories 13, 14, 15 (parallel, but after Phase 2 skills)
Phase 4 (Agents):         Story 16 → Story 17 → Story 18 → Story 19 → Story 20 → Story 21
Phase 5 (Hooks):          Story 22 (after Story 1)
Phase 6 (Terraform):      Stories 23, 24, 25 (parallel) → Story 26 → Story 27
Phase 7 (CI/CD):          Story 28, 29 (parallel, after Phase 6)
Phase 8 (Testing):        Story 30, 31 (parallel, after Phase 3 + Phase 6)
Phase 9 (Governance):     Story 32, 33 (after all phases)
```

**Critical path:** Story 1 → Story 2 → Story 4/5 → Story 6 → Story 7/8/9 → Story 13/14 → Story 19 → Story 28
