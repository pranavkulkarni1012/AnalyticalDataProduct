#!/usr/bin/env python3
"""Validate a pipeline config YAML against the JSON Schema.

Usage:
    python scripts/validate_config.py configs/my_product.yaml schemas/pipeline_config_schema.json

Exit codes:
    0 - Config is valid
    1 - Config is invalid or an error occurred
"""

import argparse
import json
import logging
import sys

import yaml
from jsonschema import Draft7Validator, ValidationError

logging.basicConfig(
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def load_yaml(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


def validate(config, schema):
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(config), key=lambda e: list(e.path))
    return errors


def main():
    parser = argparse.ArgumentParser(
        description="Validate a pipeline config YAML against JSON Schema"
    )
    parser.add_argument("config", help="Path to the config YAML file")
    parser.add_argument("schema", help="Path to the JSON Schema file")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors",
    )
    args = parser.parse_args()

    try:
        config = load_yaml(args.config)
        schema = load_json(args.schema)
    except FileNotFoundError as e:
        logger.error("File not found: %s", e.filename)
        sys.exit(1)
    except (yaml.YAMLError, json.JSONDecodeError) as e:
        logger.error("Parse error: %s", e)
        sys.exit(1)

    errors = validate(config, schema)

    if not errors:
        logger.info("Config '%s' is valid.", args.config)
        sys.exit(0)

    logger.error("Config '%s' has %d validation error(s):", args.config, len(errors))
    for i, error in enumerate(errors, 1):
        path = " -> ".join(str(p) for p in error.absolute_path) or "(root)"
        logger.error("  [%d] %s: %s", i, path, error.message)

    sys.exit(1)


if __name__ == "__main__":
    main()
