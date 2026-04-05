---
name: validate-config
description: Validates a pipeline configuration YAML against the standard schema. Use before code generation or when config is modified.
argument-hint: "[config-path]"
allowed-tools: Read Grep Bash
---

# Skill: validate-config

## Description
Validates a pipeline configuration YAML against the JSON Schema and performs semantic checks
that go beyond schema validation. This skill is the gatekeeper for all downstream pipeline
deployment -- no pipeline should be deployed from an invalid config.

The config uses the generic pipeline architecture where `source` is a single connection
object, `query.sql` contains all transformation logic, and pipeline code is shared.

## Inputs
- Pipeline config YAML path via `$ARGUMENTS`
- If no path provided, scan the `configs/` directory for `.yaml` files and validate each

## Validation Steps

Execute the following checks in order. Collect ALL errors before reporting (do not stop at
the first failure).

### Step 1: File Existence and YAML Parsing

1. Read the config file at the given path (or from `configs/` directory).
2. Verify the file exists and is valid YAML.
3. If the file cannot be parsed, report FAIL immediately with the parse error.

### Step 2: JSON Schema Validation

Run the config against `schemas/pipeline_config_schema.json` using this command:

```bash
python3 -c "
import json, yaml, sys
from jsonschema import Draft7Validator

with open('schemas/pipeline_config_schema.json') as f:
    schema = json.load(f)
with open(sys.argv[1]) as f:
    config = yaml.safe_load(f)

validator = Draft7Validator(schema)
errors = sorted(validator.iter_errors(config), key=lambda e: list(e.path))
if errors:
    for e in errors:
        path = '.'.join(str(p) for p in e.path) or '(root)'
        print(f'SCHEMA ERROR [{path}]: {e.message}')
    sys.exit(1)
else:
    print('Schema validation passed.')
" "$ARGUMENTS"
```

If schema validation fails, collect errors and continue with semantic checks.

### Step 3: Required Top-Level Keys

Verify the following required keys are present (7 required, 1 optional):
- `product` (required)
- `compute` (required)
- `source` (required) -- single object, NOT an array
- `query` (required)
- `target` (required)
- `reconciliation` (required)
- `runtime` (required)
- `data_quality` (optional but recommended -- warn if missing)

### Step 4: Product Validation

1. `product.name` matches pattern `^[a-z][a-z0-9_]{2,50}$` (snake_case, 3-51 chars).
2. `product.domain` is present and non-empty.
3. `product.version` matches semver pattern `^\d+\.\d+\.\d+$`.
4. `product.owner` is a valid email address.
5. `product.description` is non-empty.

### Step 5: Compute Validation

1. `compute.engine` is one of: `glue`, `emr`, `lambda`, `ecs`.
2. If `compute.language` is set, verify consistency:
   - `glue` or `emr` engine -> language must be `pyspark`
   - `lambda` or `ecs` engine -> language must be `python`

### Step 6: Source Validation

Validate the single `source` object (not an array):

1. `source.type` is `snowflake` (only supported source type).
2. `source.connection` is present and has required fields: `account`, `warehouse`, `role`, `authenticator`.
3. `source.connection.authenticator` must be `oauth` (no password or keypair authentication allowed).
4. If `source.connection.proxy` is present, both `source.connection.proxy.http_proxy` and `source.connection.proxy.https_proxy` must be non-empty.
5. `source.connection.account` is non-empty.
6. `source.connection.warehouse` is non-empty.
7. `source.connection.role` is non-empty.

Note: The `source` section contains connection info ONLY. There are no `database`, `schema`,
`table`, or `columns` fields -- those details are embedded in `query.sql`.

### Step 7: Query Validation

Validate the `query` section:

1. `query.sql` must be present and non-empty.
2. Trim leading whitespace from `query.sql` and verify it starts with `SELECT` or `WITH`
   (case-insensitive). If it does not, report as an ERROR.
3. **DML/DDL safety scan** -- CRITICAL: Scan `query.sql` for the following keywords
   (case-insensitive, matching as whole words or at word boundaries):
   - `INSERT`
   - `UPDATE`
   - `DELETE`
   - `MERGE`
   - `DROP`
   - `ALTER`
   - `TRUNCATE`
   - `CREATE`
   If any of these keywords are found, report as a **CRITICAL** error. Snowflake access
   is READ-ONLY. The SQL must be a pure SELECT/WITH query.
4. If `query.sql` contains subqueries or CTEs, that is acceptable as long as the
   outermost statement is SELECT/WITH and no DML/DDL keywords are present.

### Step 8: Target Validation

1. `target.catalog` is `glue_catalog`.
2. `target.s3_path` starts with `s3://`.
3. `target.format` is `iceberg` (if specified).
4. `target.write_mode` is one of: `append`, `overwrite`.
5. `target.database` and `target.table` are non-empty.

### Step 9: Reconciliation Validation

1. `reconciliation.rules` has at least one rule.
2. Each rule has: `name`, `type`, `source_expr`, `target_expr`, `tolerance_pct`.
3. `type` is one of: `row_count`, `sum`, `distinct_count`, `null_check`.
4. `tolerance_pct` is a number between 0 and 100 (inclusive).
5. `source_expr` and `target_expr` are non-empty strings.

### Step 10: Data Quality Validation (if present)

If `data_quality` section exists:
1. For each check in `data_quality.checks[]`: verify it has `name`, `type`, `column`.
2. `type` is one of: `not_null`, `unique`, `range`, `regex`, `custom`.
3. For `range` type, `parameters` must include `min` and/or `max`.
4. For `regex` type, `parameters` must include `pattern`.

### Step 11: Runtime Validation

1. `timeout_minutes` is present and between 1 and 2880 (inclusive).
2. Engine-specific required fields based on `compute.engine`:
   - **Glue**: `glue_version`, `worker_type`, `num_workers` are required.
   - **EMR**: `emr_release`, `emr_mode` are required.
   - **Lambda**: `lambda_memory_mb`, `lambda_timeout_seconds` are required.
   - **ECS**: `ecs_cpu`, `ecs_memory` are required.
3. Validate engine-specific constraints:
   - Glue: `num_workers` between 2-100, `worker_type` in (G.1X, G.2X, G.4X, G.8X, Z.2X).
   - Lambda: `lambda_memory_mb` between 128-10240, `lambda_timeout_seconds` between 1-900.
   - ECS: `ecs_cpu` in (256, 512, 1024, 2048, 4096), `ecs_memory` between 512-30720.

### Step 12: Cross-Section Consistency

1. If `product.schedule` has a `cron` expression, validate it is non-empty.
2. If `compute.schedule` has a `cron` expression, validate it is non-empty.
3. If `compute.engine` is `glue`, warn if `runtime.num_workers` > 50 (cost alert).

## Output Format

Present the validation result in this exact structure:

```
========================================
VALIDATION RESULT: [PASS|FAIL]
Config: [config-file-path]
========================================

Errors (N):
  1. [CRITICAL|ERROR] [Section.Field]: Description of the error
  2. [ERROR] [Section.Field]: Description of the error

Warnings (N):
  1. [WARN] [Section.Field]: Description of the warning

Summary:
  - Top-level keys: OK/FAIL
  - Schema validation: OK/FAIL
  - Source: Connection validated, OK/FAIL
  - Query: SQL validated, OK/FAIL (no DML/DDL detected)
  - Target: OK/FAIL
  - Reconciliation: N rules validated, OK/FAIL
  - Data Quality: N checks validated, OK/SKIPPED
  - Runtime: OK/FAIL (engine: [engine-name])
  - Cross-section consistency: OK/FAIL
========================================
```

- If there are ANY errors (CRITICAL or ERROR), the overall result is **FAIL**.
- Warnings do not cause a FAIL but should be reported.
- CRITICAL errors indicate security or compliance violations (e.g., DML/DDL in query.sql).
- Omit the Errors section entirely if there are 0 errors.
- Omit the Warnings section entirely if there are 0 warnings.
