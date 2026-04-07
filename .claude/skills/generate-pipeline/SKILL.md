---
name: generate-pipeline
description: Orchestrator skill that reads compute.engine from the pipeline config, deploys the generic pipeline for that engine, and generates the product-specific config. Use when the user wants to create or regenerate an ETL pipeline from a config.
argument-hint: "[config-path]"
allowed-tools: Read Grep Glob Write Bash
---

# Skill: generate-pipeline

## Description
Orchestrator that reads the pipeline config, validates it, determines the compute engine,
and deploys the appropriate generic pipeline. Pipeline code is GENERIC and SHARED across
all data products for a given engine. This skill does NOT generate per-product pipeline
code. Instead, it:

1. Deploys the generic pipeline template for the selected engine to `pipelines/generic/{engine}/`
2. The pipeline config YAML (with `query.sql`) IS the product-specific artifact
3. At runtime, the generic pipeline reads the config path as a parameter

After deploying the generic pipeline, this skill invokes `/generate-step-function` to
create the orchestration ASL that passes the config path to the generic pipeline at runtime.

## Architecture

- One generic pipeline per engine (Glue/EMR/Lambda/ECS) is generated into `pipelines/generic/{engine}/`
- Each data product gets its own config YAML in `configs/` with `query.sql` containing all transformation logic
- The `source` section has connection info only (not per-table definitions)
- Multiple data products = multiple configs, ONE shared pipeline codebase
- No `{{ placeholder }}` code generation -- the config file IS the product-specific artifact
- Skills contain all specifications to generate code from scratch -- no external template files needed

## Inputs
- Pipeline config YAML path via `$ARGUMENTS`
- If no path provided, scan the `configs/` directory for `.yaml` files and prompt the
  user to select one if multiple configs exist

## Steps

### Step 1: Read Pipeline Config

1. Read the pipeline config YAML from the path provided in `$ARGUMENTS`.
2. If no path is provided, use `Glob` to find `configs/*.yaml` files.
   - If exactly one config exists, use it automatically.
   - If multiple configs exist, list them and ask the user which one to use.
   - If no configs exist, report an error and stop.
3. Parse the YAML and extract all top-level sections (`product`, `compute`, `source`,
   `query`, `target`, `reconciliation`, `runtime`).

### Step 2: Validate Config

1. Invoke `/validate-config` with the config path.
2. If validation returns **FAIL**, stop and report the errors to the user.
   Do not proceed with pipeline deployment from an invalid config.
3. If validation returns **PASS** (possibly with warnings), continue.

### Step 3: Validate Connection

1. Invoke `/validate-connection` with the config path.
2. If validation returns **FAIL**, stop and report the errors to the user.
   Connection errors (wrong auth, missing proxy, write-capable roles) must be resolved
   before deploying the pipeline.
3. If validation returns **PASS** (possibly with warnings), continue.

### Step 4: Determine Compute Engine

1. Read `compute.engine` from the config.
2. Verify the engine is one of: `glue`, `emr`, `lambda`, `ecs`.
3. Read `compute.language` (if present) to confirm consistency:
   - `glue` or `emr` -> `pyspark`
   - `lambda` or `ecs` -> `python`
4. Extract `product.name` and `product.domain` for use in output paths and naming.

### Step 5: Deploy Generic Pipeline

Based on the value of `compute.engine`, generate the generic pipeline code in
`pipelines/generic/{engine}/`. If the generic pipeline directory already exists
(from a previous run), overwrite with the latest generated code.

#### Path A: `glue` (Inline Deployment)

Generate the following files in `pipelines/generic/glue/`:

1. `glue_job_boilerplate.py` -- Generic Glue ETL entrypoint using GlueContext
2. `snowflake_reader_spark.py` -- Snowflake Spark connector reader module
3. `iceberg_writer_spark.py` -- Iceberg writer using Spark `df.writeTo()`
4. `reconciliation.py` -- Shared reconciliation logic (PySpark variant)
5. `data_quality.py` -- Shared data quality checks (duck-typed for Spark/Pandas)
6. `parameter_utils.py` -- Shared parameter substitution module (see below)

#### parameter_utils.py Specification

This shared module provides safe SQL parameter substitution for all engines:

```python
"""
Safe SQL parameter substitution for runtime parameters.
Replaces ${param_name} placeholders in SQL with validated, escaped values.
"""
import re
from datetime import date, datetime


def substitute_parameters(sql, parameters, param_definitions):
    """
    Substitute ${param_name} placeholders in SQL with runtime parameter values.

    Args:
        sql: SQL string with ${param_name} placeholders
        parameters: dict of {param_name: param_value} from runtime input
        param_definitions: list of parameter dicts from config (name, type, default, required)

    Returns:
        SQL string with all placeholders replaced

    Raises:
        ValueError: If a required parameter is missing or type validation fails
    """
    # Build effective parameter values: runtime overrides > defaults
    effective = {}
    for defn in param_definitions:
        name = defn["name"]
        param_type = defn["type"]
        required = defn.get("required", True)
        default = defn.get("default")

        if name in parameters:
            value = parameters[name]
        elif default is not None:
            value = default
        elif required:
            raise ValueError(f"Required parameter '{name}' not provided and has no default")
        else:
            continue  # optional param not provided, leave placeholder (or skip)

        # Type validation and safe formatting
        effective[name] = _format_value(name, value, param_type)

    # Replace all ${param_name} placeholders
    def replacer(match):
        param_name = match.group(1)
        if param_name not in effective:
            raise ValueError(f"Undeclared parameter '${{{param_name}}}' found in SQL")
        return effective[param_name]

    return re.sub(r'\$\{(\w+)\}', replacer, sql)


def _format_value(name, value, param_type):
    """Validate and format a parameter value based on its declared type."""
    value_str = str(value)
    if param_type == "string":
        escaped = value_str.replace("'", "''")
        return f"'{escaped}'"
    elif param_type == "date":
        # Validate ISO date format (YYYY-MM-DD)
        try:
            datetime.strptime(value_str, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Parameter '{name}' must be a valid date (YYYY-MM-DD), got '{value_str}'")
        return f"'{value_str}'"
    elif param_type == "integer":
        try:
            int(value_str)
        except ValueError:
            raise ValueError(f"Parameter '{name}' must be an integer, got '{value_str}'")
        return value_str
    elif param_type == "number":
        try:
            float(value_str)
        except ValueError:
            raise ValueError(f"Parameter '{name}' must be a number, got '{value_str}'")
        return value_str
    elif param_type == "boolean":
        if value_str.lower() in ("true", "1", "yes"):
            return "TRUE"
        elif value_str.lower() in ("false", "0", "no"):
            return "FALSE"
        else:
            raise ValueError(f"Parameter '{name}' must be a boolean, got '{value_str}'")
    else:
        raise ValueError(f"Unknown parameter type '{param_type}' for parameter '{name}'")
```

The boilerplate must handle parameter substitution as follows:
```python
from parameter_utils import substitute_parameters

# Read parameter definitions from config (empty list if section absent)
param_definitions = config.get("parameters", [])

# Read runtime parameter values from engine-specific input (empty dict if not provided)
# Glue: json.loads(args.get("--parameters", "{}"))
# EMR/ECS: json.loads(args.parameters) if args.parameters else {}
# Lambda: event.get("parameters", {})
runtime_parameters = ...  # engine-specific

# Substitute -- safe no-op when param_definitions is empty (no parameters declared)
resolved_sql = substitute_parameters(config["query"]["sql"], runtime_parameters, param_definitions)

# Also apply to reconciliation source_expr
for rule in config.get("reconciliation", {}).get("rules", []):
    rule["source_expr"] = substitute_parameters(
        rule["source_expr"], runtime_parameters, param_definitions
    )
```

When `param_definitions` is an empty list (no `parameters` section in config),
`substitute_parameters()` returns the SQL unchanged -- no placeholders to replace,
no parameters to validate. This makes it safe to call unconditionally.

The generic Glue pipeline must:
- Use `GlueContext`, `Job.init()`/`Job.commit()`, and `getResolvedOptions`
- Take `--config-path` argument (S3 or local path to the YAML config)
- Read the config at runtime to determine source connection, query SQL, target table
- Read runtime parameters from Glue job arguments (prefixed `--param_`) and merge with
  parameter defaults from the config's `parameters` section
- Substitute `${param_name}` placeholders in `query.sql` using a safe `substitute_parameters()`
  function that validates types and escapes values (see CLAUDE.md Runtime Parameters)
- Execute the resolved SQL against Snowflake via the Spark Snowflake connector
- Write results to the Iceberg target defined in the config via `df.writeTo()`
- Run reconciliation checks defined in the config (with same parameter substitution applied
  to `source_expr` in reconciliation rules)
- Use structured logging with correlation ID
- Include top-level try/except with `exc_info=True` and re-raise

#### Path B: `emr`

1. Invoke `/generate-emr-pipeline` with the config path.
2. The EMR skill deploys the generic EMR pipeline to `pipelines/generic/emr/`.

#### Path C: `lambda`

1. Invoke `/generate-lambda-pipeline` with the config path.
2. The Lambda skill deploys the generic Lambda pipeline to `pipelines/generic/lambda/`.

#### Path D: `ecs`

1. Invoke `/generate-ecs-pipeline` with the config path.
2. The ECS skill deploys the generic ECS pipeline to `pipelines/generic/ecs/`.

### Step 6: Generate Step Function

1. Invoke `/generate-step-function` with the config path.
2. The Step Function skill creates an ASL JSON definition at
   `pipelines/{product.name}/step_functions/{product.name}_orchestrator.asl.json`.
3. The ASL passes the config path as a parameter to the generic pipeline at runtime:
   - `glue` -> `arn:aws:states:::glue:startJobRun.sync` with `--config-path` argument
   - `emr` -> `arn:aws:states:::elasticmapreduce:addStep.sync` with `--config-path` argument
   - `lambda` -> `arn:aws:states:::lambda:invoke` with `config_path` in event payload
   - `ecs` -> `arn:aws:states:::ecs:runTask.sync` with `--config-path` argument

### Step 7: Cross-Cutting Verification

Verify that the generic pipeline templates include all of the following cross-cutting
concerns. If any are missing from the templates, report a warning:

1. **Structured logging**: Correlation ID (UUID) set at the start of execution.
   Log format: `%(asctime)s | %(levelname)s | {correlation_id} | %(message)s`

2. **Error handling**: Top-level try/except block around all data processing.
   The except block must log the error with `exc_info=True` and re-raise.

3. **Config-driven execution**: The pipeline reads the config YAML at runtime
   and extracts source, query, target, and reconciliation settings.

4. **Reconciliation calls**: If `reconciliation.rules` exist in the config:
   - For Glue/EMR (Spark): inline reconciliation checks using the Snowflake
     Spark connector for source queries and `spark.sql()` for target queries.
   - For Lambda/ECS: synchronous invocation of the reconciliation Lambda.

5. **Runtime parameter substitution**: If `parameters` section exists in the config:
   - Parameters are read from engine-specific runtime input (Glue job args, Lambda event, etc.)
   - `substitute_parameters()` is called on `query.sql` and reconciliation `source_expr`
   - All parameter values are type-validated and safely escaped before substitution
   - Missing required parameters cause the pipeline to fail fast with a clear error

## Output Summary

After all deployment steps complete, present a summary:

```
========================================
PIPELINE DEPLOYMENT COMPLETE
Config: [config-file-path]
Engine: [compute.engine]
========================================

Generic Pipeline:
  Location: pipelines/generic/[engine]/
  Files:
    1. [list of deployed template files]

Product Config:
  Config: [config-file-path]
  Query: [first 80 chars of query.sql]...

Orchestration:
  Step Function: pipelines/{product.name}/step_functions/{product.name}_orchestrator.asl.json

Validation:
  - Config validation: [PASS | PASS (N warnings)]
  - Connection validation: [PASS | PASS (N warnings)]

Config Summary:
  - Source: Snowflake ({source.connection.account}) with OAuth + proxy
  - Query: SQL-based transformation ({N} lines)
  - Target: {target.database}.{target.table} (Iceberg on S3)
  - Reconciliation: [N] checks defined
  - Logging: Structured with correlation ID
  - Error handling: Built into generic pipeline

Next Steps:
  - Review config in configs/{product.name}.yaml
  - Generic pipeline is shared -- do not modify per product
  - Run /generate-terraform to create infrastructure
  - Deploy via CI/CD pipeline
========================================
```
