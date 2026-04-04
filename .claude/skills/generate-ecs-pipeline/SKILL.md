---
name: generate-ecs-pipeline
description: Generates a Python+Pandas ECS Fargate task from a pipeline config. Includes Dockerfile and entrypoint script. Use when compute.engine is ecs.
argument-hint: "[config-path]"
allowed-tools: Read Grep Glob Write Bash
---

# Skill: generate-ecs-pipeline

## Description
Generates a containerized Python+Pandas ETL job for ECS Fargate. This skill is
invoked by `/generate-pipeline` when `compute.engine` is `ecs`.

Uses the same Python+Pandas pattern as Lambda (shared `snowflake_reader_pandas.py`,
`iceberg_writer_pyiceberg.py`) but runs as a Docker container with no timeout limit.

## Prerequisites
This skill assumes `/validate-config` and `/validate-connection` have already run and
passed (normally invoked by `/generate-pipeline` before delegation). If invoked directly,
run both validators first.

## Key Differences from Lambda
- No timeout limit (unlike Lambda's 15 minutes).
- Runs as a Docker container on ECS Fargate.
- Entry point is a standalone Python script (`main.py`), not a Lambda handler.
- Generates a Dockerfile based on corporate base image from ECR.
- Suitable for medium-to-large datasets that exceed Lambda memory limits.
- Generates three output files: entrypoint, Dockerfile, requirements.txt.

## Inputs
- Pipeline config YAML path via `$ARGUMENTS`
- If no path provided, scan the `configs/` directory for `.yaml` files

## Templates
Read these templates if available for boilerplate patterns. Generate code directly
from config values regardless of whether templates exist.

- `templates/python/ecs_entrypoint.py` -- ECS-specific boilerplate
- `templates/python/Dockerfile` -- Dockerfile template
- `templates/python/snowflake_reader_pandas.py` -- shared with Lambda
- `templates/python/iceberg_writer_pyiceberg.py` -- shared with Lambda
- `templates/common/reconciliation.py` -- shared reconciliation logic

## Output
- `pipelines/{product.name}/ecs_jobs/{product.name}_main.py` (entrypoint)
- `pipelines/{product.name}/ecs_jobs/Dockerfile`
- `pipelines/{product.name}/ecs_jobs/requirements.txt`

## Code Generation Steps

### Sub-step 1: Generate Entrypoint Script

Generate a standalone Python script with `if __name__ == "__main__"` entry point.
The entrypoint uses the same Python+Pandas patterns as the Lambda skill but with
a `main()` function instead of `handler(event, context)`.

**Module docstring**: Include job name, product info, "ECS Fargate -- Python+Pandas".

**Imports** (same as Lambda):
```python
import os, sys, logging, uuid, json, argparse
from datetime import datetime
import boto3
import snowflake.connector
import pandas as pd
from pyiceberg.catalog import load_catalog
import pyarrow as pa
```

**Argument parsing**:
```python
def parse_args():
    parser = argparse.ArgumentParser(description=f"ECS ETL job for {product_name}")
    parser.add_argument("--env",
        default=os.environ.get("ENV", "prod"),
        help="Environment (dev/staging/prod)")
    parser.add_argument("--job-name",
        default="adp-{product.domain}-{product.name}-etl-prod",
        help="Job name for logging")
    args = parser.parse_args()
    return args
```

Use `parser.parse_args()` (not `parse_known_args()`) so misspelled arguments
cause an immediate, descriptive error. Read `--env` default from the `ENV`
environment variable (set in the ECS task definition) to keep the Docker
image environment-agnostic.

**Main function structure**:
```python
def main():
    args = parse_args()
    correlation_id = str(uuid.uuid4())
    # ... logging setup ...
    logger.info(f"Starting ECS job {args.job_name} in environment {args.env}")
    logger.info(f"Correlation ID: {correlation_id}")

    try:
        # ... data processing (same as Lambda sub-steps 6-11) ...
        logger.info("Job completed successfully.")
        sys.exit(0)
    except Exception as e:
        logger.error("Job failed. See traceback below.", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
```

Key ECS-specific patterns:
- Use `sys.exit(0)` on success and `sys.exit(1)` on failure for container exit codes.
- ECS/Step Functions detect failure via non-zero exit code.
- No Lambda-style JSON return -- exit codes are the signal.
- Do NOT include `str(e)` in log messages -- use `exc_info=True` instead
  and rely on `correlation_id` to correlate back to CloudWatch logs.

### Sub-step 2: Data Processing (Shared with Lambda)

The data processing logic inside the `try` block is identical to the Lambda skill
(Sub-steps 6-11 in `/generate-lambda-pipeline`). **Do not copy the Lambda import
block -- use the ECS import block from Sub-step 1 above, which includes `sys`
and `argparse`.**

- **Source reading**: Snowflake via `snowflake-connector-python` + `cursor.fetch_pandas_all()`
  with OAuth token from Secrets Manager, proxy env vars.
  Note: `connection` is nested inside each source entry (`sources[N].connection.*`),
  not at the top level of the config. The DBAPI connector uses `proxy_host`/`proxy_port`
  only (not `use_proxy`, which is a Spark connector key).
- **Joins**: `pandas.merge()` with `how` mapping (`full` -> `outer`).
- **Column mappings**: Direct pandas operations (e.g., `pd.to_datetime().dt.to_period()`).
  Do NOT use `pd.eval()` for SQL-style expressions.
- **Aggregations**: `pandas.groupby().agg()` with function mapping
  (`count_distinct` -> `nunique`, `avg` -> `mean`).
- **Filters**: `df.query()` or boolean indexing for post-aggregation filters.
- **Iceberg write**: `pyiceberg` catalog + `table.overwrite()`/`table.append()`.
  **ECS override**: Read AWS region from
  `os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION"))` rather
  than `os.environ["AWS_REGION"]`. ECS Fargate does not automatically set
  `AWS_REGION` the same way Lambda does -- it is typically available as
  `AWS_DEFAULT_REGION` or must be injected via the task definition.
- **Reconciliation**: Invoke reconciliation Lambda via `boto3.client("lambda").invoke()`
  with `InvocationType="RequestResponse"`. Check `response.get("FunctionError")`
  before reading the payload. Read payload once with `.read().decode("utf-8")`.
  **ECS override**: On reconciliation failure, do NOT use Lambda's `return {...}`
  pattern. Instead call `sys.exit(1)` -- return values from `main()` are ignored
  by the container runtime. On reconciliation success, continue to `sys.exit(0)`.
  If `reconciliation.rules` is empty or absent, log a warning and skip.

Refer to `/generate-lambda-pipeline` for the detailed implementation of each
sub-step, applying the ECS overrides noted above.

### Sub-step 3: Generate Dockerfile

Generate a production-ready Dockerfile that must pass `hadolint`:

```dockerfile
# Use corporate base image from ECR
FROM {ecr_registry}/python:3.11-slim

# Create non-root user early (before COPY/RUN as that user)
RUN useradd -m appuser

# Set working directory
WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code with correct ownership
COPY --chown=appuser:appuser {product.name}_main.py .

# Switch to non-root user
USER appuser

# Entry point (--env is read from ENV environment variable by default)
CMD ["python", "{product.name}_main.py"]
```

Corporate Dockerfile requirements:
- Use corporate base image from ECR (not public Docker Hub).
- Run as non-root user for security. Create user before COPY of application
  code and use `--chown=appuser:appuser` on COPY to ensure correct ownership.
- Use `--no-cache-dir` with pip to reduce image size.
- Layer ordering: COPY requirements.txt before application code for caching.
- Must pass `hadolint` (the `post-codegen-docker-lint.sh` hook will check this).
- Do NOT hardcode `--env prod` in CMD -- the environment is read from the
  `ENV` environment variable (set in the ECS task definition) by `parse_args()`.
- For batch ECS tasks (run-task, not services), `HEALTHCHECK` is not required
  and is ignored by the ECS scheduler. Omit it for batch tasks. If the container
  will be run as an ECS service, add a meaningful health check in the task
  definition instead.

Derive `{ecr_registry}` from `compute.ecr_registry` in the pipeline config.
If absent, use the placeholder `{aws_account_id}.dkr.ecr.{aws_region}.amazonaws.com`
and emit a warning.

### Sub-step 4: Generate requirements.txt

Same as Lambda:
```
snowflake-connector-python[pandas]>=3.0.0
pandas>=2.0.0
pyiceberg[glue]>=0.5.0
pyarrow>=12.0.0
boto3>=1.28.0
```

## Cross-Cutting Concerns

1. **Structured logging**: Correlation ID per invocation via `logging.LoggerAdapter`.
   Formatter: `%(asctime)s | %(levelname)s | %(correlation_id)s | %(message)s`.

2. **Error handling**: Top-level try/except in `main()`. Use `sys.exit(1)` on failure
   (ECS/Step Functions detect via container exit code). Do NOT include `str(e)`
   in log messages -- use `exc_info=True` and rely on `correlation_id` to
   correlate back to CloudWatch logs.

3. **Reconciliation**: Synchronously invoke the reconciliation Lambda
   (`adp-{product.name}-recon-{env}`) using `InvocationType="RequestResponse"`.
   Check `response.get("FunctionError")` before reading the payload. On failure,
   call `sys.exit(1)` (not `return` -- ECS signals failure via exit code).

4. **Connection safety**: Use context managers (`with ... as conn:`) for
   Snowflake connections to ensure cleanup on exceptions. Pass `database`
   and `schema` as `connect()` parameters.

## Output Summary

```
========================================
ECS PIPELINE GENERATION COMPLETE
Config: [config-file-path]
Engine: ecs
========================================

Generated Files:
  1. pipelines/{product.name}/ecs_jobs/{product.name}_main.py (entrypoint)
  2. pipelines/{product.name}/ecs_jobs/Dockerfile
  3. pipelines/{product.name}/ecs_jobs/requirements.txt
  3. pipelines/{product.name}/ecs_jobs/requirements.txt

Key Differences from Lambda:
  - Standalone main.py (not Lambda handler)
  - Docker container on ECS Fargate
  - No timeout limit
  - sys.exit() for exit codes

Features:
  - Sources: [N] Snowflake sources via DBAPI + pandas
  - Joins: [N] via pandas.merge()
  - Aggregations: [N] via pandas.groupby().agg()
  - Reconciliation: Lambda invocation
  - Logging: Structured with correlation ID
  - Dockerfile: Corporate base image, hadolint-compliant

Next Steps:
  - Review generated code
  - Build and push Docker image to ECR
  - Run /generate-step-function for orchestration
  - Run /generate-terraform for infrastructure
========================================
```
