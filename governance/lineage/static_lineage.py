"""
Static Lineage Generator

Derives source-to-target column mappings from the pipeline config YAML
at code-generation time. Produces a structured JSON lineage document
that can be stored alongside Iceberg table metadata or published to
a lineage catalog.

In the SQL-driven architecture, lineage is derived from the query.sql
field and the source connection config, rather than from structured
transformations. Table references and column aliases are extracted from
the SQL using pattern matching.

Used by the Spec Generator Agent and Pipeline Generator Agent.

Usage:
    python governance/lineage/static_lineage.py --config configs/my_product.yaml
    python governance/lineage/static_lineage.py --config configs/my_product.yaml --output lineage.json
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
    """Load and return the pipeline config YAML."""
    with open(path, "r") as f:
        return yaml.safe_load(f)


def extract_source_lineage(config):
    """
    Extract source metadata from the config.

    Parses fully-qualified table references from query.sql and combines
    with source connection info.
    """
    sources = []
    source_conn = config.get("source", {})
    sql = config.get("query", {}).get("sql", "")

    # Extract fully-qualified table references (DATABASE.SCHEMA.TABLE)
    fqn_pattern = re.compile(
        r'"?(\w+)"?\."?(\w+)"?\."?(\w+)"?',
    )
    seen = set()
    for match in fqn_pattern.finditer(sql):
        db, schema, table = match.group(1), match.group(2), match.group(3)
        key = f"{db}.{schema}.{table}"
        if key not in seen:
            seen.add(key)
            sources.append({
                "name": table.lower(),
                "system": source_conn.get("type", "snowflake"),
                "database": db,
                "schema": schema,
                "table": table,
                "connection_account": source_conn.get("connection", {}).get("account", ""),
            })

    return sources


def extract_target_lineage(config):
    """Extract target metadata from the config."""
    target = config.get("target", {})
    return {
        "catalog": target.get("catalog", "glue_catalog"),
        "database": target.get("database"),
        "table": target.get("table"),
        "s3_path": target.get("s3_path"),
        "format": target.get("format", "iceberg"),
        "write_mode": target.get("write_mode"),
        "partition_by": target.get("partition_by", []),
        "sort_order": target.get("sort_order", []),
    }


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


def extract_column_mappings(config):
    """
    Derive source-to-target column mappings from query.sql.

    Parses the final SELECT clause to extract column expressions and
    their aliases, producing a lineage graph from SQL expressions to
    target column names.
    """
    mappings = []
    sql = config.get("query", {}).get("sql", "")
    if not sql:
        return mappings

    # Extract the final SELECT clause
    select_pattern = re.compile(
        r'\bSELECT\b(.*?)(?:\bFROM\b)',
        re.IGNORECASE | re.DOTALL,
    )
    matches = select_pattern.findall(sql)
    if not matches:
        return mappings

    final_select = matches[-1]
    col_exprs = _split_select_columns(final_select)

    for expr in col_exprs:
        expr = expr.strip()
        if not expr:
            continue

        # Extract alias
        alias_match = re.search(r'\bAS\s+(\w+)\s*$', expr, re.IGNORECASE)
        if alias_match:
            col_name = alias_match.group(1)
            source_expr = expr[:alias_match.start()].strip()
        else:
            ident_match = re.search(r'(\w+)\s*$', expr)
            col_name = ident_match.group(1) if ident_match else expr.strip()
            source_expr = expr.strip()

        # Determine mapping type from expression
        upper = source_expr.upper()
        if re.search(r'\bSUM\b|\bAVG\b|\bCOUNT\b|\bMIN\b|\bMAX\b', upper):
            mapping_type = "aggregation"
        elif re.search(r'\bDATE_TRUNC\b', upper):
            mapping_type = "date_transform"
        else:
            mapping_type = "column_reference"

        mappings.append({
            "source": source_expr,
            "target": col_name,
            "transformation": source_expr,
            "type": mapping_type,
        })

    return mappings


def extract_cte_lineage(config):
    """Extract CTE definitions from the SQL query."""
    ctes = []
    sql = config.get("query", {}).get("sql", "")
    if not sql:
        return ctes

    # Extract CTE names from WITH clause
    cte_pattern = re.compile(
        r'\b(\w+)\s+AS\s*\(',
        re.IGNORECASE,
    )
    for match in cte_pattern.finditer(sql):
        cte_name = match.group(1)
        # Skip SQL keywords that might match
        if cte_name.upper() not in ('SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'NOT'):
            ctes.append({"name": cte_name})

    return ctes


def generate_lineage(config):
    """
    Generate the complete static lineage document from a pipeline config.

    Returns a structured dict suitable for JSON serialization.
    """
    product = config.get("product", {})

    lineage = {
        "metadata": {
            "product_name": product.get("name"),
            "domain": product.get("domain"),
            "version": product.get("version"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "static_lineage",
            "config_version": product.get("version", "0.0.0"),
        },
        "sources": extract_source_lineage(config),
        "target": extract_target_lineage(config),
        "ctes": extract_cte_lineage(config),
        "column_mappings": extract_column_mappings(config),
        "query_sql": config.get("query", {}).get("sql", ""),
        "query_description": config.get("query", {}).get("description", ""),
    }

    return lineage


def main():
    parser = argparse.ArgumentParser(
        description="Generate static lineage from a pipeline config YAML"
    )
    parser.add_argument("--config", required=True, help="Path to config YAML")
    parser.add_argument("--output", help="Output JSON file (default: stdout)")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except FileNotFoundError:
        logger.error("Config file not found: %s", args.config)
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error("Failed to parse config: %s", e)
        sys.exit(1)

    lineage = generate_lineage(config)
    lineage_json = json.dumps(lineage, indent=2)

    if args.output:
        with open(args.output, "w") as f:
            f.write(lineage_json)
        logger.info("Lineage written to %s", args.output)
    else:
        print(lineage_json)

    logger.info(
        "Generated lineage: %d sources, %d CTEs, %d column mappings",
        len(lineage["sources"]),
        len(lineage["ctes"]),
        len(lineage["column_mappings"]),
    )


if __name__ == "__main__":
    main()
