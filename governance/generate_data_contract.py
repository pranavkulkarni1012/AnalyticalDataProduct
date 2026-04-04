"""
Data Contract Generator

Populates the data contract template from a pipeline config YAML,
producing a concrete data contract for a specific data product.
The generated contract can be published to Confluence via the
Spec Generator Agent.

Usage:
    python governance/generate_data_contract.py --config configs/monthly_revenue_by_category.yaml
    python governance/generate_data_contract.py --config configs/my_product.yaml --output contracts/my_product.yaml
"""
import argparse
import json
import logging
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
    Infer the target table column schema from transformations.

    Derives column names, types, and nullability from aggregation
    metrics, column mappings, and group-by clauses.
    """
    columns = []
    transformations = config.get("transformations", {})

    # Columns from aggregation metrics
    for agg in transformations.get("aggregations", []):
        for metric in agg.get("metrics", []):
            col_type = "double" if metric["function"] in ("sum", "avg") else "long"
            columns.append({
                "name": metric["alias"],
                "type": col_type,
                "nullable": False,
                "description": f"{metric['function'].upper()}({metric['column']})",
            })

    # Columns from column_mappings
    for cm in transformations.get("column_mappings", []):
        # Infer type from expression -- default to string
        col_type = "string"
        expr = cm.get("expression", "")
        if "DATE_TRUNC" in expr.upper() or "DATE" in expr.upper():
            col_type = "date"
        columns.append({
            "name": cm["target"],
            "type": col_type,
            "nullable": False,
            "description": cm.get("expression", cm["source"]),
        })

    return columns


def build_source_lineage(config):
    """Build source lineage entries from config sources."""
    entries = []
    for source in config.get("sources", []):
        cols = source.get("columns", [])
        if isinstance(cols, str):
            cols = ["*"]
        entries.append({
            "name": source["name"],
            "system": "snowflake",
            "database": source["database"],
            "schema": source["schema"],
            "table": source["table"],
            "columns": cols,
        })
    return entries


def build_column_mappings(config):
    """Build column lineage mappings from transformations."""
    mappings = []
    transformations = config.get("transformations", {})

    for cm in transformations.get("column_mappings", []):
        mappings.append({
            "source": cm["source"],
            "target": cm["target"],
            "transformation": cm.get("expression", cm["source"]),
        })

    for agg in transformations.get("aggregations", []):
        for metric in agg.get("metrics", []):
            mappings.append({
                "source": metric["column"],
                "target": metric["alias"],
                "transformation": f"{metric['function'].upper()}({metric['column']})",
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
