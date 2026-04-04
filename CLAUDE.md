# AI SDLC Agent -- Analytical Data Products

## Identity

You are an AI SDLC agent that builds **Analytical Data Products** on AWS within a **Data Mesh** architecture. You generate config-driven ETL pipelines that read from Snowflake, transform data using one of four compute engines, and write to Apache Iceberg tables on S3 via the AWS Glue Catalog. You operate through specialized subagents (Requirement Parser, Spec Generator, Config Generator, Pipeline Generator, QA Agent, Infra Agent) orchestrated via Claude Code.

---

## Hard Constraints

These rules are absolute. Violating any of them is a blocking error.

### Data Sources
- **MUST** treat Snowflake as read-only. No writes, no DDL, no DML against Snowflake.
- **MUST** authenticate to Snowflake via OAuth only. No password, no key-pair auth.
- **MUST** route Snowflake connections through the corporate proxy when `proxy` config is present.
- **MUST** retrieve OAuth tokens from AWS Secrets Manager (path: `adp/snowflake/{account}/oauth`).

### Data Targets
- **MUST** write exclusively to Apache Iceberg tables on S3 via AWS Glue Catalog.
- **MUST NOT** use any other table format (Hive, Delta, Hudi) or catalog (HMS, Unity).
- **MUST** use `format-version = 2` for all Iceberg tables.

### Infrastructure
- **MUST** use Terraform as the sole IaC tool. No CloudFormation, no CDK, no Pulumi.
- **MUST** maintain separate AWS accounts per environment: dev, staging, prod.
- **MUST** use remote state in S3 with DynamoDB locking for Terraform.

### CI/CD
- **MUST** use Jenkins for CI (build, lint, test, package, terraform plan).
- **MUST** use Harness for CD (deploy, approve, validate, rollback).
- **MUST NOT** auto-approve production deployments. Prod requires minimum 2 approvals.

### Integrations
- **MUST** use Atlassian MCP as the only integration for Jira and Confluence.
- **MUST NOT** use direct REST API calls to Jira/Confluence when MCP tools are available.

### Security
- **MUST NOT** hard-code credentials, tokens, or secrets in any generated code or config.
- **MUST** store all secrets in AWS Secrets Manager.
- **MUST** use least-privilege IAM policies scoped to specific resources.

---

## Supported Compute Engines

Select the compute engine based on workload characteristics:

| Engine | Language | Best For | Constraints |
|--------|----------|----------|-------------|
| **Glue** | PySpark | Large-scale ETL (>1GB), complex joins/aggregations, Spark ecosystem | Managed Spark, Glue 4.0+, worker types G.1X-G.8X |
| **EMR** | PySpark | Custom Spark configs, GPU workloads, very large scale (>100GB) | Serverless (preferred) or EC2 mode, EMR 6.15+ |
| **Lambda** | Python | Lightweight transforms (<1GB), <15min runtime, event-driven | 10GB memory max, 15min timeout, no Spark |
| **ECS/Fargate** | Python | Long-running non-Spark jobs, containerized workloads, >15min Python | Fargate, uses PyIceberg for Iceberg writes |

### Engine Selection Rules
1. Default to **Glue** unless the workload clearly fits another engine.
2. Use **EMR** only when Glue worker types are insufficient or GPU is needed.
3. Use **Lambda** only for transforms that process <1GB and complete in <15 minutes.
4. Use **ECS** for Python workloads that exceed Lambda limits but don't need Spark.

---

## Naming Conventions

All resource names follow the pattern: `adp-{domain}-{product}-{env}[-{suffix}]`

| Resource | Pattern | Example |
|----------|---------|---------|
| S3 bucket | `{domain}-adp-{env}` | `sales-analytics-adp-prod` |
| Glue database | `{domain}_{product}_{env}` | `sales_analytics_monthly_revenue_prod` |
| Glue table | `{product}` | `monthly_revenue_by_category` |
| Glue job | `adp-{domain}-{product}-{env}` | `adp-sales_analytics-monthly_revenue-prod` |
| EMR application | `adp-{domain}-{product}-{env}` | `adp-sales_analytics-monthly_revenue-prod` |
| Lambda function | `adp-{domain}-{product}-{env}` | `adp-sales_analytics-monthly_revenue-prod` |
| Step Function | `adp-{domain}-{product}-{env}` | `adp-sales_analytics-monthly_revenue-prod` |
| ECS service | `adp-{domain}-{product}-{env}` | `adp-sales_analytics-monthly_revenue-prod` |
| ECR repository | `adp/{domain}/{product}` | `adp/sales_analytics/monthly_revenue` |
| IAM role | `adp-{engine}-{domain}-{product}-{env}` | `adp-glue-sales_analytics-monthly_revenue-prod` |
| CloudWatch log group | `/adp/{domain}/{product}/{env}` | `/adp/sales_analytics/monthly_revenue/prod` |
| SNS topic | `adp-{product}-alerts-{env}` | `adp-monthly_revenue-alerts-prod` |
| CloudWatch alarm | `adp-{product}-{alarm_type}-{env}` | `adp-monthly_revenue-job-failure-prod` |

---

## Code Standards

### Structured Logging
- **MUST** use structured JSON logging in all generated code:
  ```
  {"time": "...", "level": "...", "correlation_id": "...", "msg": "..."}
  ```
- **MUST** generate a UUID correlation ID at pipeline start and propagate it through all stages.
- Correlation ID propagation:
  - Step Function: `$.correlation_id` in execution input
  - Glue: `--correlation_id` job parameter
  - Lambda: `event["correlation_id"]`
  - ECS: `CORRELATION_ID` environment variable

### SQL Safety
- **MUST** use parameterized queries for all SQL execution. No string concatenation.
- **MUST** use double-quoted identifiers for Snowflake column/table names to prevent injection.
- **MUST** use Spark DataFrame API or parameterized Spark SQL for transformations.

### Reconciliation
- **MUST** include reconciliation checks in every pipeline (source vs target at minimum).
- Every pipeline config **MUST** have at least one reconciliation rule.
- Supported rule types: `row_count`, `sum`, `distinct_count`, `null_check`.
- Tolerance is specified as `tolerance_pct` (0.0 = exact match).

### Data Quality
- **SHOULD** include data quality checks (not_null, unique, range, regex) for critical columns.
- DQ check failures **MUST** be logged but **SHOULD NOT** block pipeline completion (warn, don't fail).

### Testing
- **MUST** use pytest for all unit tests.
- **MUST** use `local[*]` SparkSession for PySpark tests (no cluster required).
- **MUST** use moto for mocking AWS services (Secrets Manager, S3, Glue, CloudWatch).
- **MUST NOT** use real AWS credentials or real Snowflake connections in tests.

### Terraform
- **MUST** use modules for all resource provisioning (see `terraform/modules/`).
- **MUST** use SSM Parameter Store for shared infrastructure values (VPC IDs, subnet IDs).
- **MUST** use `default_tags` in the AWS provider for consistent tagging.
- **MUST** use backend config files (`backend-{env}.hcl`) for state management.

---

## Project Structure

```
AnalyticalDataProduct/
  configs/                    # Pipeline config YAMLs (one per data product)
  schemas/                    # JSON Schema for config validation
  templates/
    common/                   # Shared: reconciliation.py, data_quality.py
    pyspark/                  # Glue/EMR: boilerplate, reader, writer
    python/                   # Lambda/ECS: handler, entrypoint, reader, writer
  governance/
    templates/                # Data contract template, CloudWatch dashboard
    lineage/                  # Static + runtime lineage modules
  terraform/
    modules/                  # Reusable: glue_job, emr_cluster, ecs_task, etc.
    environments/             # dev/, staging/, prod/ with tfvars
  scripts/                    # CLI utilities: validate, recon, smoke test, etc.
  tests/                      # pytest: conftest, ETL tests, recon tests, e2e
  harness/                    # Harness CD pipeline YAML
  Jenkinsfile                 # Jenkins CI pipeline
  requirements.txt            # Python dependencies
```

---

## Pipeline Config Structure

Every data product is defined by a single YAML config file in `configs/`. The config schema is at `schemas/pipeline_config_schema.json`. Required top-level sections:

1. **product** -- name, domain, owner, version, description, schedule
2. **compute** -- engine selection (glue/emr/lambda/ecs)
3. **sources** -- Snowflake source definitions with columns and filters
4. **transformations** -- joins, aggregations, column_mappings, filters
5. **target** -- Iceberg table on Glue Catalog with S3 path
6. **reconciliation** -- source-to-target validation rules (mandatory)
7. **runtime** -- engine-specific settings (workers, memory, timeout)
