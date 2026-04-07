---
name: generate-ecs-pipeline
description: Generates the generic ECS Fargate Python+Pandas pipeline with Dockerfile and shared modules in pipelines/generic/ecs/. Use when compute.engine is ecs.
argument-hint: "[config-path]"
allowed-tools: Read Grep Glob Write Bash
---

# Skill: generate-ecs-pipeline

## Description
Generates the generic ECS Fargate Python+Pandas pipeline code and writes it to
`pipelines/generic/ecs/`. Pipeline code is GENERIC and SHARED -- this skill does NOT
generate per-product code. The generic pipeline reads a config YAML at runtime (passed
via `--config-path` argument) to determine source connection, query SQL, target table,
and reconciliation rules.

Uses the same Python+Pandas pattern as Lambda (shared reader/writer modules) but runs
as a Docker container with no timeout limit.

This skill is invoked by `/generate-pipeline` when `compute.engine` is `ecs`.

## Architecture

- The generic ECS pipeline is a standalone Python script running in a Docker container
- At runtime, it takes `--config-path` (S3 path) and `--env` as arguments
- It downloads the config YAML, executes `query.sql` against Snowflake, writes to Iceberg
- One generic Docker image serves ALL ECS-based data products
- The config YAML (with `query.sql`) is the only product-specific artifact

## Prerequisites
This skill assumes `/validate-config` and `/validate-connection` have already run and
passed (normally invoked by `/generate-pipeline` before delegation). If invoked directly,
run both validators first.

## Key Differences from Lambda
- No timeout limit (unlike Lambda's 15 minutes).
- Runs as a Docker container on ECS Fargate.
- Entry point is a standalone Python script (`ecs_entrypoint.py`), not a Lambda handler.
- Includes a Dockerfile based on corporate base image from ECR.
- Uses `sys.exit(0)`/`sys.exit(1)` for exit codes (not Lambda JSON returns).
- Suitable for medium-to-large datasets that exceed Lambda limits.

## Inputs
- Pipeline config YAML path via `$ARGUMENTS`
- If no path provided, scan the `configs/` directory for `.yaml` files

## Steps

### Step 1: Read Pipeline Config

1. Read the pipeline config YAML from `$ARGUMENTS` (or scan `configs/`).
2. Parse and extract `product`, `compute`, `source`, `query`, `target`,
   `reconciliation`, `runtime` sections.
3. Verify `compute.engine` is `ecs`.

### Step 2: Generate Generic ECS Pipeline

Generate the following files in `pipelines/generic/ecs/`:

1. `ecs_entrypoint.py` -- Standalone Python entrypoint with argparse (`--config-path`, `--env`, `--param_*`)
2. `snowflake_reader_pandas.py` -- Snowflake DBAPI reader using `cursor.fetch_pandas_all()`
3. `iceberg_writer_pyiceberg.py` -- PyIceberg writer using Glue Catalog
4. `reconciliation.py` -- Shared reconciliation logic (Python+Pandas variant)
5. `data_quality.py` -- Shared data quality checks (duck-typed for Spark/Pandas)
6. `parameter_utils.py` -- Shared parameter substitution module (same as Glue; see `/generate-pipeline` SKILL.md for full specification)

Create the `pipelines/generic/ecs/` directory if it does not exist. If it already
exists, overwrite with the latest code.

### Step 3: Generate Dockerfile

Generate a Dockerfile at `pipelines/generic/ecs/Dockerfile`.

The Dockerfile must meet corporate requirements:
- Use corporate base image from ECR (not public Docker Hub).
- Run as non-root user for security.
- Use `--no-cache-dir` with pip to reduce image size.
- Layer ordering: COPY requirements.txt before application code for caching.
- Must pass `hadolint`.
- Do NOT hardcode `--env` in CMD -- the environment is read from the `ENV`
  environment variable (set in the ECS task definition).
- The entrypoint accepts `--config-path` as a runtime argument.

Derive `{ecr_registry}` from `runtime.ecr_registry` in the pipeline config.
If absent, use placeholder `{aws_account_id}.dkr.ecr.{aws_region}.amazonaws.com`
and emit a warning.

### Step 4: Generate requirements.txt

Generate a `requirements.txt` at `pipelines/generic/ecs/requirements.txt`:

```
snowflake-connector-python[pandas]>=3.0.0
pandas>=2.0.0
pyiceberg[glue]>=0.5.0
pyarrow>=12.0.0
boto3>=1.28.0
pyyaml>=6.0
```

Note: `pyyaml` is included because the generic pipeline parses the config YAML at runtime.

### Step 5: Verify Generic Pipeline Content

Read the deployed `ecs_entrypoint.py` and verify it includes:

1. **Config-driven execution**: The entrypoint reads `--config-path` from argparse,
   downloads the config YAML from S3, and loads source, query, target, and
   reconciliation settings at runtime.

2. **Runtime parameter substitution**: If the config has a `parameters` section,
   reads `--param_{name}` arguments via argparse, merges with defaults from config,
   and calls `substitute_parameters()` on `query.sql` and reconciliation `source_expr`
   before execution. Uses `parameter_utils.py` for safe type-validated substitution.

3. **Source reading**: Connects to Snowflake using OAuth (token from Secrets Manager)
   with proxy support via `snowflake-connector-python`. Uses `source.connection`
   from the config (single source object).

4. **Query execution**: Executes the resolved `query.sql` from the config against Snowflake via
   the DBAPI cursor. Uses `cursor.fetch_pandas_all()` for the result set.

5. **Iceberg write**: Uses `pyiceberg` catalog to write results to the target table.
   Reads AWS region from `os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION"))`.

6. **Reconciliation**: Synchronous invocation of the reconciliation Lambda.
   Parameter substitution applied to `source_expr` before execution.
   On failure, calls `sys.exit(1)` (not Lambda-style `return`).

7. **Structured logging**: Correlation ID per execution via `logging.LoggerAdapter`.

8. **Error handling**: Top-level try/except in `main()`. Uses `sys.exit(1)` on failure.

9. **Connection safety**: Context managers for Snowflake connections.

If any of these are missing from the template, report a warning.

## Cross-Cutting Concerns

1. **Structured logging**: Correlation ID per execution via `logging.LoggerAdapter`.
   Formatter: `%(asctime)s | %(levelname)s | %(correlation_id)s | %(message)s`.

2. **Error handling**: Top-level try/except in `main()`. Use `sys.exit(1)` on failure
   (ECS/Step Functions detect via container exit code).

3. **Reconciliation**: Synchronously invoke the reconciliation Lambda. On failure,
   call `sys.exit(1)`.

4. **Connection safety**: Use context managers for Snowflake connections.

5. **Config-driven**: All product-specific behavior comes from the config YAML.
   No hardcoded product names, table names, or SQL in the pipeline code.

## Output Summary

```
========================================
ECS GENERIC PIPELINE DEPLOYED
Config: [config-file-path]
Engine: ecs
========================================

Generic Pipeline:
  Location: pipelines/generic/ecs/
  Files:
    1. ecs_entrypoint.py (generic ECS entrypoint)
    2. snowflake_reader_pandas.py (shared pandas reader)
    3. iceberg_writer_pyiceberg.py (shared PyIceberg writer)
    4. reconciliation.py (shared reconciliation)
    5. data_quality.py (shared data quality)
    6. Dockerfile (corporate base image, hadolint-compliant)
    7. requirements.txt (Python dependencies)

Runtime Behavior:
  - Entrypoint reads config from --config-path at runtime
  - Downloads config YAML from S3
  - Executes query.sql from config against Snowflake
  - Writes results to Iceberg target defined in config
  - Invokes reconciliation Lambda with rules from config

Key Properties:
  - Standalone ecs_entrypoint.py (not Lambda handler)
  - Docker container on ECS Fargate
  - No timeout limit
  - sys.exit() for exit codes
  - Config-driven: no per-product code generation

Next Steps:
  - Generic pipeline is shared -- do not modify per product
  - Product config: [config-file-path]
  - Build and push Docker image to ECR
  - Run task with --config-path s3://... --env {env} --param_load_date 2026-03-31
  - Runtime parameter substitution via parameter_utils.py
========================================
```
