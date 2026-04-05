---
name: generate-emr-pipeline
description: Deploys the generic EMR PySpark pipeline by copying templates and shared modules to pipelines/generic/emr/. Use when compute.engine is emr.
argument-hint: "[config-path]"
allowed-tools: Read Grep Glob Write Bash
---

# Skill: generate-emr-pipeline

## Description
Deploys the generic EMR PySpark pipeline by copying template files and shared modules
to `pipelines/generic/emr/`. Pipeline code is GENERIC and SHARED -- this skill does NOT
generate per-product code. The generic pipeline reads a config YAML at runtime (passed
via `--config-path` argument) to determine source connection, query SQL, target table,
and reconciliation rules.

This skill is invoked by `/generate-pipeline` when `compute.engine` is `emr`.

## Architecture

- The generic EMR pipeline is a standalone PySpark script using `SparkSession` (no GlueContext)
- At runtime, it takes `--config-path` (S3 or local path) and `--env` as arguments
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

### Step 2: Deploy Generic EMR Pipeline

Copy the following files from `templates/` to `pipelines/generic/emr/`:

1. `templates/pyspark/emr_job_boilerplate.py` -> `pipelines/generic/emr/emr_job_boilerplate.py`
2. `templates/pyspark/snowflake_reader_spark.py` -> `pipelines/generic/emr/snowflake_reader_spark.py`
3. `templates/pyspark/iceberg_writer_spark.py` -> `pipelines/generic/emr/iceberg_writer_spark.py`
4. `templates/common/reconciliation.py` -> `pipelines/generic/emr/reconciliation.py`
5. `templates/common/data_quality.py` -> `pipelines/generic/emr/data_quality.py`

Create the `pipelines/generic/emr/` directory if it does not exist. If it already
exists, overwrite with the latest templates.

### Step 3: Verify Generic Pipeline Content

Read the deployed `emr_job_boilerplate.py` and verify it includes:

1. **Config-driven execution**: The boilerplate reads a config YAML path from
   `--config-path` argument and loads source, query, target, and reconciliation
   settings at runtime.

2. **SparkSession with Iceberg catalog**: Configured via `SparkSession.builder.config()`
   using catalog settings from the config's `target.catalog`.

3. **Source reading**: Connects to Snowflake using OAuth (token from Secrets Manager)
   with proxy support. Uses `source.connection` from the config (single source object).

4. **Query execution**: Executes `query.sql` from the config against Snowflake via
   the Spark Snowflake connector. The SQL must be a SELECT/WITH statement.

5. **Iceberg write**: Writes results to `{target.catalog}.{target.database}.{target.table}`
   using `df.writeTo()` with the configured `write_mode`.

6. **Reconciliation**: Inline checks using Snowflake Spark connector for source
   queries and `spark.sql()` for target queries.

7. **Structured logging**: Correlation ID, log format
   `%(asctime)s | %(levelname)s | {correlation_id} | %(message)s`.

8. **Error handling**: Top-level try/except/finally. The finally block calls
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
  - argparse with --config-path and --env
  - if __name__ == "__main__" entry point
  - spark.stop() in finally block
  - Config-driven: no per-product code generation

Next Steps:
  - Generic pipeline is shared -- do not modify per product
  - Product config: [config-file-path]
  - Submit via EMR step (EC2) or EMR Serverless job run
  - Pass --config-path s3://bucket/configs/{product.name}.yaml --env {env}
========================================
```
