---
name: generate-lambda-pipeline
description: Generates the generic Lambda Python+Pandas pipeline with shared modules in pipelines/generic/lambda/. Use when compute.engine is lambda.
argument-hint: "[config-path]"
allowed-tools: Read Grep Glob Write Bash
---

# Skill: generate-lambda-pipeline

## Description
Generates the generic Lambda Python+Pandas pipeline code and writes it to
`pipelines/generic/lambda/`. Pipeline code is GENERIC and SHARED -- this skill does NOT
generate per-product code. The generic pipeline reads a config YAML at runtime (passed
via `config_path` in the Lambda event payload) to determine source connection, query SQL,
target table, and reconciliation rules.

Uses `snowflake-connector-python` (DBAPI) for Snowflake reads and `pyiceberg` for
Iceberg writes. All transformations live in `query.sql` within the config -- no Spark dependency.

This skill is invoked by `/generate-pipeline` when `compute.engine` is `lambda`.

## Architecture

- The generic Lambda pipeline is a handler that reads a config path from the event payload
- At runtime, `event["config_path"]` points to the product-specific config YAML (S3 path)
- It downloads the config, executes `query.sql` against Snowflake, writes to Iceberg
- One generic Lambda function serves ALL Lambda-based data products
- The config YAML (with `query.sql`) is the only product-specific artifact

## Prerequisites
This skill assumes `/validate-config` and `/validate-connection` have already run and
passed (normally invoked by `/generate-pipeline` before delegation). If invoked directly,
run both validators first.

## Key Differences from PySpark (Glue/EMR)
- No Spark -- uses **pandas DataFrames** for all data handling.
- Snowflake reads via `snowflake-connector-python` (DBAPI cursor, not Spark connector).
- Iceberg writes via `pyiceberg` library (not Spark `writeTo`).
- Lambda handler signature: `handler(event, context)`.
- 15-minute timeout and 10 GB memory limit.
- Config path passed via `event["config_path"]`.

## Inputs
- Pipeline config YAML path via `$ARGUMENTS`
- If no path provided, scan the `configs/` directory for `.yaml` files

## Steps

### Step 1: Read Pipeline Config

1. Read the pipeline config YAML from `$ARGUMENTS` (or scan `configs/`).
2. Parse and extract `product`, `compute`, `source`, `query`, `target`,
   `reconciliation`, `runtime` sections.
3. Verify `compute.engine` is `lambda`.

### Step 2: Generate Generic Lambda Pipeline

Generate the following files in `pipelines/generic/lambda/`:

1. `lambda_handler.py` -- Generic Lambda handler with `handler(event, context)` signature
2. `snowflake_reader_pandas.py` -- Snowflake DBAPI reader using `cursor.fetch_pandas_all()`
3. `iceberg_writer_pyiceberg.py` -- PyIceberg writer using Glue Catalog
4. `reconciliation.py` -- Shared reconciliation logic (Python+Pandas variant)
5. `data_quality.py` -- Shared data quality checks (duck-typed for Spark/Pandas)
6. `parameter_utils.py` -- Shared parameter substitution module (same as Glue; see `/generate-pipeline` SKILL.md for full specification)

Create the `pipelines/generic/lambda/` directory if it does not exist. If it already
exists, overwrite with the latest code.

### Step 3: Generate requirements.txt

Generate a `requirements.txt` at `pipelines/generic/lambda/requirements.txt`:

```
snowflake-connector-python[pandas]>=3.0.0
pandas>=2.0.0
pyiceberg[glue]>=0.5.0
pyarrow>=12.0.0
boto3>=1.28.0
pyyaml>=6.0
```

Note: `pyyaml` is included because the generic pipeline parses the config YAML at runtime.

### Step 4: Verify Generic Pipeline Content

Read the deployed `lambda_handler.py` and verify it includes:

1. **Config-driven execution**: The handler reads `config_path` from the Lambda event
   payload, downloads the config YAML from S3, and loads source, query, target, and
   reconciliation settings at runtime.

2. **Runtime parameter substitution**: If the config has a `parameters` section,
   reads `event["parameters"]` dict, merges with defaults from config, and calls
   `substitute_parameters()` on `query.sql` and reconciliation `source_expr` before
   execution. Uses `parameter_utils.py` for safe type-validated substitution.

3. **Source reading**: Connects to Snowflake using OAuth (token from Secrets Manager)
   with proxy support via `snowflake-connector-python`. Uses `source.connection`
   from the config (single source object).

4. **Query execution**: Executes the resolved `query.sql` from the config against Snowflake via
   the DBAPI cursor. Uses `cursor.fetch_pandas_all()` for the result set.

5. **Iceberg write**: Uses `pyiceberg` catalog to write results to the target table.

6. **Reconciliation**: Synchronous invocation of the reconciliation Lambda.
   Parameter substitution applied to `source_expr` before execution.

7. **Structured logging**: Correlation ID per invocation via `logging.LoggerAdapter`.
   Formatter: `%(asctime)s | %(levelname)s | %(correlation_id)s | %(message)s`.

8. **Error handling**: Top-level try/except in handler. Return structured JSON
   response with statusCode 200 (success) or 500 (failure).

9. **Connection safety**: Context managers for Snowflake connections.

If any of these are missing from the template, report a warning.

## Cross-Cutting Concerns

1. **Structured logging**: Correlation ID per invocation via `logging.LoggerAdapter`.

2. **Error handling**: Top-level try/except in handler. Return structured JSON response.
   Do NOT re-raise -- Lambda uses return values for error signaling.

3. **Reconciliation**: Synchronously invoke the reconciliation Lambda using
   `InvocationType="RequestResponse"`.

4. **Connection safety**: Use context managers (`with ... as conn:`) for Snowflake
   connections.

5. **Config-driven**: All product-specific behavior comes from the config YAML.
   No hardcoded product names, table names, or SQL in the pipeline code.

## Output Summary

```
========================================
LAMBDA GENERIC PIPELINE DEPLOYED
Config: [config-file-path]
Engine: lambda
========================================

Generic Pipeline:
  Location: pipelines/generic/lambda/
  Files:
    1. lambda_handler.py (generic Lambda handler)
    2. snowflake_reader_pandas.py (shared pandas reader)
    3. iceberg_writer_pyiceberg.py (shared PyIceberg writer)
    4. reconciliation.py (shared reconciliation)
    5. data_quality.py (shared data quality)
    6. requirements.txt (Python dependencies)

Runtime Behavior:
  - Handler reads config_path from event payload
  - Downloads config YAML from S3
  - Executes query.sql from config against Snowflake
  - Writes results to Iceberg target defined in config
  - Invokes reconciliation Lambda with rules from config

Key Properties:
  - pandas DataFrames (no Spark)
  - snowflake-connector-python (DBAPI)
  - pyiceberg for Iceberg writes
  - handler(event, context) entry point
  - Config-driven: no per-product code generation

Next Steps:
  - Generic pipeline is shared -- do not modify per product
  - Product config: [config-file-path]
  - Package as Lambda deployment (zip or container)
  - Invoke with {"config_path": "s3://...", "env": "{env}", "parameters": {"load_date": "2026-03-31"}}
  - Runtime parameter substitution via parameter_utils.py
========================================
```
