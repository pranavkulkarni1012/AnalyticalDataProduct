---
name: generate-emr-pipeline
description: Generates the generic EMR PySpark pipeline with shared modules in pipelines/generic/emr/. Use when compute.engine is emr.
argument-hint: "[config-path]"
allowed-tools: Read Grep Glob Write Bash
---

# Skill: generate-emr-pipeline

## Description
Generates the generic EMR PySpark pipeline code and writes it to
`pipelines/generic/emr/`. Pipeline code is GENERIC and SHARED -- this skill does NOT
generate per-product code. The generic pipeline reads a config YAML at runtime (passed
via `--config-path` argument) to determine source connection, query SQL, target table,
and reconciliation rules.

This skill is invoked by `/generate-pipeline` when `compute.engine` is `emr`.

## Architecture

- The generic EMR pipeline is a standalone PySpark script using `SparkSession` (no GlueContext)
- At runtime, it takes `--config-path` (S3 or local path) and `--env` (DEV|TEST|PROD, defaults to DEV) as arguments
- It reads `--env`, defaulting to `DEV` if not provided. Logs the environment at startup.
  The ENV value is set by Terraform when deploying the EMR job (see `/generate-terraform`).
- It reads the config YAML, executes `query.sql` against Snowflake, writes to Iceberg
- One generic pipeline serves ALL EMR-based data products
- The config YAML (with `query.sql`) is the only product-specific artifact

## Prerequisites
This skill assumes `/validate-config` and `/validate-connection` have already run and
passed (normally invoked by `/generate-pipeline` before delegation). If invoked directly,
run both validators first.

## Key Differences from Glue
- No `GlueContext`, no `job.init()`/`job.commit()` -- uses plain `SparkSession`.
- Iceberg catalog configured via `SparkSession.builder.config()`.
- Entry point uses `if __name__ == "__main__"` pattern with `argparse`.
- Arguments parsed via `argparse` (not Glue's `getResolvedOptions`).
- `SparkSession.stop()` called in a `finally` block for cleanup.

## Inputs
- Pipeline config YAML path via `$ARGUMENTS`
- If no path provided, scan the `configs/` directory for `.yaml` files

## Steps

### Step 1: Read Pipeline Config

1. Read the pipeline config YAML from `$ARGUMENTS` (or scan `configs/`).
2. Parse and extract `product`, `compute`, `source`, `query`, `target`,
   `reconciliation`, `runtime` sections.
3. Verify `compute.engine` is `emr`.

### Step 2: Generate Generic EMR Pipeline

Generate the following files in `pipelines/generic/emr/`:

1. `emr_job_boilerplate.py` -- Generic EMR entrypoint using SparkSession (not GlueContext)
2. `snowflake_reader_spark.py` -- Snowflake Spark connector reader module
3. `iceberg_writer_spark.py` -- Iceberg writer using Spark `df.writeTo()`
4. `reconciliation.py` -- Shared reconciliation logic (PySpark variant)
5. `data_quality.py` -- Shared data quality checks (duck-typed for Spark/Pandas)
6. `parameter_utils.py` -- Shared parameter substitution module (same as Glue; see `/generate-pipeline` SKILL.md for full specification)

Create the `pipelines/generic/emr/` directory if it does not exist. If it already
exists, overwrite with the latest code.

### Step 3: Verify Generic Pipeline Content

Read the deployed `emr_job_boilerplate.py` and verify it includes:

1. **Config-driven execution**: The boilerplate reads a config YAML path from
   `--config-path` argument and loads source, query, target, and reconciliation
   settings at runtime.

2. **SparkSession with Iceberg catalog**: Configured via `SparkSession.builder.config()`
   using catalog settings from the config's `target.catalog`.

3. **Source reading**: Connects to Snowflake using OAuth (token from Secrets Manager)
   with proxy support. Uses `source.connection` from the config (single source object).

4. **Runtime parameter substitution**: If the config has a `parameters` section,
   reads `--param_{name}` arguments via argparse, merges with defaults from config,
   and calls `substitute_parameters()` on `query.sql` and reconciliation `source_expr`
   before execution. Uses `parameter_utils.py` for safe type-validated substitution.

5. **Query execution**: Executes the resolved `query.sql` from the config against Snowflake via
   the Spark Snowflake connector. The SQL must be a SELECT/WITH statement.

6. **Iceberg write**: Writes results to `{target.catalog}.{target.database}.{target.table}`
   using `df.writeTo()` with the configured `write_mode`.

7. **Reconciliation**: Inline checks using Snowflake Spark connector for source
   queries and `spark.sql()` for target queries. Parameter substitution applied
   to `source_expr` before execution.

8. **Structured logging**: Correlation ID, log format
   `%(asctime)s | %(levelname)s | {correlation_id} | %(message)s`.

9. **Error handling**: Top-level try/except/finally. The finally block calls
   `spark.stop()` guarded with `if spark:`.

If any of these are missing from the template, report a warning.

## Cross-Cutting Concerns

The generic EMR pipeline template must include:

1. **Structured logging**: Correlation ID per execution, log messages at key points
   (job start, config loaded, source read, query execution, write, recon, end).

2. **Error handling**: Top-level try/except/finally. The except block logs
   with `exc_info=True` and re-raises. The finally block calls `spark.stop()`.

3. **Config-driven**: All product-specific behavior comes from the config YAML.
   No hardcoded product names, table names, or SQL in the pipeline code.

4. **Reconciliation**: Inline checks reading rules from the config at runtime.

## Output Summary

After deployment, present:

```
========================================
EMR GENERIC PIPELINE DEPLOYED
Config: [config-file-path]
Engine: emr
========================================

Generic Pipeline:
  Location: pipelines/generic/emr/
  Files:
    1. emr_job_boilerplate.py (generic EMR entrypoint)
    2. snowflake_reader_spark.py (shared Spark reader)
    3. iceberg_writer_spark.py (shared Iceberg writer)
    4. reconciliation.py (shared reconciliation)
    5. data_quality.py (shared data quality)

Runtime Behavior:
  - Pipeline reads config from --config-path at runtime
  - Executes query.sql from config against Snowflake
  - Writes results to Iceberg target defined in config
  - Runs reconciliation checks defined in config

Key Properties:
  - SparkSession (no GlueContext)
  - argparse with --config-path, --env, and --param_* for runtime parameters
  - if __name__ == "__main__" entry point
  - Runtime parameter substitution via parameter_utils.py
  - spark.stop() in finally block
  - Config-driven: no per-product code generation

Next Steps:
  - Generic pipeline is shared -- do not modify per product
  - Product config: [config-file-path]
  - Submit via EMR step (EC2) or EMR Serverless job run
  - Pass --config-path s3://bucket/configs/{product.name}.yaml --env {env}
========================================
```
