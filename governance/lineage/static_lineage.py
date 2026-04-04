"""
Static Lineage Generator

Derives source-to-target column mappings from the pipeline config YAML
at code-generation time. Produces a structured JSON lineage document
that can be stored alongside Iceberg table metadata or published to
a lineage catalog.

Used by the Spec Generator Agent and Pipeline Generator Agent.

Usage:
    python governance/lineage/static_lineage.py --config configs/my_product.yaml
    python governance/lineage/static_lineage.py --config configs/my_product.yaml --output lineage.json
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
    """Load and return the pipeline config YAML."""
    with open(path, "r") as f:
        return yaml.safe_load(f)


def extract_source_lineage(config):
    """
    Extract source metadata from the config.

    Returns a list of source descriptors with system, database, schema,
    table, and column information.
    """
    sources = []
    for source in config.get("sources", []):
        columns = source.get("columns", [])
        if isinstance(columns, str) and columns == "*":
            columns = ["*"]

        sources.append({
            "name": source["name"],
            "system": source.get("type", "snowflake"),
            "database": source["database"],
            "schema": source["schema"],
            "table": source["table"],
            "columns": columns,
            "filters": source.get("filters", []),
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


def extract_column_mappings(config):
    """
    Derive source-to-target column mappings from transformations.

    Traces columns through joins, aggregations, and column_mappings
    to produce a lineage graph from source columns to target columns.
    """
    mappings = []
    transformations = config.get("transformations", {})

    # Direct column mappings (explicit rename/expression)
    for cm in transformations.get("column_mappings", []):
        mappings.append({
            "source": cm["source"],
            "target": cm["target"],
            "transformation": cm.get("expression", cm["source"]),
            "type": "column_mapping",
        })

    # Aggregation-derived mappings
    for agg in transformations.get("aggregations", []):
        for metric in agg.get("metrics", []):
            mappings.append({
                "source": metric["column"],
                "target": metric["alias"],
                "transformation": f"{metric['function'].upper()}({metric['column']})",
                "type": "aggregation",
            })
        # Group-by columns are pass-through
        for group_col in agg.get("group_by", []):
            mappings.append({
                "source": group_col,
                "target": group_col,
                "transformation": "GROUP_BY",
                "type": "group_by",
            })

    return mappings


def extract_join_lineage(config):
    """Extract join relationship metadata."""
    joins = []
    for join in config.get("transformations", {}).get("joins", []):
        joins.append({
            "left": join["left"],
            "right": join["right"],
            "type": join["type"],
            "keys": [
                {"left_key": k["left_key"], "right_key": k["right_key"]}
                for k in join.get("keys", [])
            ],
        })
    return joins


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
        "joins": extract_join_lineage(config),
        "column_mappings": extract_column_mappings(config),
        "filters": {
            "source_filters": {
                source["name"]: source.get("filters", [])
                for source in config.get("sources", [])
            },
            "post_transform_filters": config.get("transformations", {}).get(
                "filters", []
            ),
        },
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
        "Generated lineage: %d sources, %d joins, %d column mappings",
        len(lineage["sources"]),
        len(lineage["joins"]),
        len(lineage["column_mappings"]),
    )


if __name__ == "__main__":
    main()
