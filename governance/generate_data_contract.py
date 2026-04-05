"""
Data Contract Generator

Populates the data contract template from a pipeline config YAML,
producing a concrete data contract for a specific data product.
The generated contract can be published to Confluence via the
Spec Generator Agent.

In the SQL-driven architecture, column schema and lineage are derived
from the query.sql field and the source connection config, rather than
from structured transformations.

Usage:
    python governance/generate_data_contract.py --config configs/monthly_revenue_by_category.yaml
    python governance/generate_data_contract.py --config configs/my_product.yaml --output contracts/my_product.yaml
"""
import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone

import yaml

logging.basicConfig(
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def load_config(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def infer_column_schema(config):
    """
    Infer the target table column schema from query.sql.

    Parses the final SELECT clause of the SQL to extract column aliases
    and infer types from common SQL patterns (SUM -> double, COUNT -> long, etc.).
    """
    columns = []
    sql = config.get("query", {}).get("sql", "")
    if not sql:
        return columns

    # Extract the outermost SELECT clause (last SELECT in the SQL)
    # This heuristic works for CTE-based queries where the final SELECT
    # produces the output columns
    select_pattern = re.compile(
        r'\bSELECT\b(.*?)(?:\bFROM\b)',
        re.IGNORECASE | re.DOTALL,
    )
    matches = select_pattern.findall(sql)
    if not matches:
        return columns

    # Use the last SELECT clause (the final output)
    final_select = matches[-1]

    # Split by comma, handling nested parentheses
    col_exprs = _split_select_columns(final_select)

    for expr in col_exprs:
        expr = expr.strip()
        if not expr:
            continue

        # Extract alias (AS alias_name)
        alias_match = re.search(r'\bAS\s+(\w+)\s*$', expr, re.IGNORECASE)
        if alias_match:
            col_name = alias_match.group(1)
        else:
            # Use the last identifier as the column name
            ident_match = re.search(r'(\w+)\s*$', expr)
            col_name = ident_match.group(1) if ident_match else expr.strip()

        # Infer type from expression
        col_type = _infer_type_from_expr(expr)

        columns.append({
            "name": col_name,
            "type": col_type,
            "nullable": False,
            "description": expr.strip(),
        })

    return columns


def _split_select_columns(select_clause):
    """Split a SELECT clause by commas, respecting parentheses nesting."""
    parts = []
    depth = 0
    current = []
    for char in select_clause:
        if char == '(':
            depth += 1
            current.append(char)
        elif char == ')':
            depth -= 1
            current.append(char)
        elif char == ',' and depth == 0:
            parts.append(''.join(current))
            current = []
        else:
            current.append(char)
    if current:
        parts.append(''.join(current))
    return parts


def _infer_type_from_expr(expr):
    """Infer SQL column type from expression patterns."""
    upper = expr.upper()
    if re.search(r'\bSUM\b', upper) or re.search(r'\bAVG\b', upper):
        return "double"
    if re.search(r'\bCOUNT\b', upper):
        return "long"
    if re.search(r'\bDATE_TRUNC\b', upper) or re.search(r'\bDATE\b', upper):
        return "date"
    if re.search(r'\bMIN\b', upper) or re.search(r'\bMAX\b', upper):
        return "double"
    return "string"


def build_source_lineage(config):
    """Build source lineage from source connection and query SQL.

    Extracts table references from the SQL query using fully-qualified
    name patterns (DATABASE.SCHEMA.TABLE).
    """
    entries = []
    source = config.get("source", {})
    sql = config.get("query", {}).get("sql", "")

    # Extract fully-qualified table references from SQL
    # Matches patterns like "DATABASE"."SCHEMA"."TABLE" or DATABASE.SCHEMA.TABLE
    fqn_pattern = re.compile(
        r'"?(\w+)"?\."?(\w+)"?\."?(\w+)"?',
    )
    seen = set()
    for match in fqn_pattern.finditer(sql):
        db, schema, table = match.group(1), match.group(2), match.group(3)
        key = f"{db}.{schema}.{table}"
        if key not in seen:
            seen.add(key)
            entries.append({
                "name": table.lower(),
                "system": "snowflake",
                "database": db,
                "schema": schema,
                "table": table,
                "connection_account": source.get("connection", {}).get("account", ""),
            })

    return entries


def build_column_mappings(config):
    """Build column lineage mappings from the SQL query.

    Extracts column aliases from the final SELECT clause of the SQL.
    """
    mappings = []
    columns = infer_column_schema(config)
    for col in columns:
        mappings.append({
            "source": col["description"],
            "target": col["name"],
            "transformation": col["description"],
        })
    return mappings


def build_quality_section(config):
    """Build the quality thresholds section."""
    recon = config.get("reconciliation", {})
    dq = config.get("data_quality", {})

    null_limits = {}
    for check in dq.get("checks", []):
        if check["type"] == "not_null":
            null_limits[check["column"]] = 0.0

    recon_rules = []
    for rule in recon.get("rules", []):
        recon_rules.append({
            "name": rule["name"],
            "type": rule["type"],
            "tolerance_pct": rule.get("tolerance_pct", 0.0),
        })

    dq_checks = []
    for check in dq.get("checks", []):
        entry = {
            "name": check["name"],
            "type": check["type"],
            "column": check["column"],
        }
        if check.get("parameters"):
            entry["parameters"] = check["parameters"]
        dq_checks.append(entry)

    return {
        "row_count": {"min": 1, "max": None},
        "null_percentage_limits": null_limits,
        "reconciliation": {
            "enabled": recon.get("enabled", True),
            "tolerance_pct": 0.01,
            "rules": recon_rules,
        },
        "data_quality_checks": dq_checks,
    }


def generate_contract(config):
    """Generate a complete data contract from a pipeline config."""
    product = config.get("product", {})
    target = config.get("target", {})
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    contract = {
        "contract": {
            "version": product.get("version", "1.0.0"),
            "created_at": now,
            "updated_at": now,
            "status": "active",
        },
        "product": {
            "name": product.get("name"),
            "domain": product.get("domain"),
            "owner": product.get("owner"),
            "description": product.get("description", "").strip(),
            "tags": product.get("tags", {}),
        },
        "schema": {
            "catalog": target.get("catalog", "glue_catalog"),
            "database": target.get("database"),
            "table": target.get("table"),
            "format": target.get("format", "iceberg"),
            "columns": infer_column_schema(config),
            "partition_by": target.get("partition_by", []),
            "sort_order": target.get("sort_order", []),
        },
        "sla": {
            "freshness": {
                "max_age_hours": 24,
                "schedule": product.get("schedule", {}).get("cron", ""),
                "timezone": "UTC",
            },
            "availability": {
                "uptime_pct": 99.5,
                "maintenance_window": "Sun 02:00-04:00 UTC",
            },
            "latency": {
                "max_pipeline_duration_minutes": config.get("runtime", {}).get(
                    "timeout_minutes", 120
                ),
                "p95_duration_minutes": config.get("runtime", {}).get(
                    "timeout_minutes", 120
                )
                // 2,
            },
        },
        "quality": build_quality_section(config),
        "lineage": {
            "sources": build_source_lineage(config),
            "target": {
                "catalog": target.get("catalog", "glue_catalog"),
                "database": target.get("database"),
                "table": target.get("table"),
                "s3_path": target.get("s3_path"),
            },
            "column_mappings": build_column_mappings(config),
            "query_sql": config.get("query", {}).get("sql", ""),
        },
        "support": {
            "owner_team": product.get("owner"),
            "slack_channel": f"#{product.get('domain', 'data')}-data",
            "on_call_rotation": f"{product.get('domain', 'data')}-oncall",
            "escalation_policy": "Page owner team if SLA breach > 2 hours",
        },
    }

    return contract


def main():
    parser = argparse.ArgumentParser(
        description="Generate a data contract from a pipeline config YAML"
    )
    parser.add_argument("--config", required=True, help="Path to config YAML")
    parser.add_argument("--output", help="Output YAML file (default: stdout)")
    parser.add_argument(
        "--format",
        choices=["yaml", "json"],
        default="yaml",
        help="Output format (default: yaml)",
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except FileNotFoundError:
        logger.error("Config file not found: %s", args.config)
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error("Failed to parse config: %s", e)
        sys.exit(1)

    contract = generate_contract(config)

    if args.format == "json":
        output = json.dumps(contract, indent=2)
    else:
        output = yaml.dump(contract, default_flow_style=False, sort_keys=False)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        logger.info("Data contract written to %s", args.output)
    else:
        print(output)

    logger.info(
        "Generated data contract for '%s' (v%s): %d columns, %d recon rules, %d DQ checks",
        contract["product"]["name"],
        contract["contract"]["version"],
        len(contract["schema"]["columns"]),
        len(contract["quality"]["reconciliation"]["rules"]),
        len(contract["quality"]["data_quality_checks"]),
    )


if __name__ == "__main__":
    main()
