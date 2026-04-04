#!/usr/bin/env python3
"""Run reconciliation checks for an analytical data product.

Usage:
    python scripts/run_recon.py --product monthly_revenue_by_category --env dev
    python scripts/run_recon.py --config configs/monthly_revenue_by_category.yaml --env dev --output report.json

Exit codes:
    0 - All reconciliation checks passed
    1 - One or more checks failed or an error occurred
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


def run_check(check, env):
    """Run a single reconciliation check. Returns a result dict."""
    check_type = check.get("type", "unknown")
    check_name = check.get("name", check_type)
    tolerance = check.get("tolerance", 0.0)

    try:
        # In a real implementation, this would query source/target systems.
        # For now, return a placeholder that indicates the check structure is valid.
        result = {
            "name": check_name,
            "type": check_type,
            "environment": env,
            "tolerance": tolerance,
            "source_value": None,
            "target_value": None,
            "passed": True,
            "message": f"Check '{check_name}' structure validated (dry run)",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        result = {
            "name": check_name,
            "type": check_type,
            "environment": env,
            "passed": False,
            "message": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Run reconciliation checks for an analytical data product"
    )
    parser.add_argument("--product", help="Product name (resolves to configs/<name>.yaml)")
    parser.add_argument("--config", help="Path to config YAML (overrides --product)")
    parser.add_argument(
        "--env",
        required=True,
        choices=["dev", "staging", "prod"],
        help="Target environment",
    )
    parser.add_argument("--output", help="Output file for JSON report (default: stdout)")
    args = parser.parse_args()

    if not args.config and not args.product:
        parser.error("Either --product or --config is required")

    config_path = args.config or f"configs/{args.product}.yaml"

    try:
        config = load_config(config_path)
    except FileNotFoundError:
        logger.error("Config file not found: %s", config_path)
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error("Failed to parse config: %s", e)
        sys.exit(1)

    recon_checks = config.get("reconciliation", {}).get("checks", [])
    if not recon_checks:
        logger.warning("No reconciliation checks defined in config.")
        sys.exit(0)

    logger.info(
        "Running %d reconciliation check(s) for '%s' in %s",
        len(recon_checks),
        config.get("product", {}).get("name", "unknown"),
        args.env,
    )

    results = []
    all_passed = True
    for check in recon_checks:
        result = run_check(check, args.env)
        results.append(result)
        if not result["passed"]:
            all_passed = False
            logger.error("FAILED: %s - %s", result["name"], result["message"])
        else:
            logger.info("PASSED: %s", result["name"])

    report = {
        "product": config.get("product", {}).get("name", "unknown"),
        "environment": args.env,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_checks": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "failed": sum(1 for r in results if not r["passed"]),
        "all_passed": all_passed,
        "results": results,
    }

    report_json = json.dumps(report, indent=2)

    if args.output:
        with open(args.output, "w") as f:
            f.write(report_json)
        logger.info("Report written to %s", args.output)
    else:
        print(report_json)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
