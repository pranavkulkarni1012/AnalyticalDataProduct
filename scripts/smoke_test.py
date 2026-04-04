#!/usr/bin/env python3
"""Post-deployment smoke test for analytical data products.

Checks:
1. Iceberg table exists in Glue Catalog
2. Table has recent data (within configurable window)
3. CloudWatch alarms are in OK state

Usage:
    python scripts/smoke_test.py --product monthly_revenue_by_category --env prod
    python scripts/smoke_test.py --product my_product --env dev --max-age-hours 24

Exit codes:
    0 - All checks passed
    1 - One or more checks failed or an error occurred
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone

import boto3
import yaml

import uuid as _uuid

_CORRELATION_ID = str(_uuid.uuid4())

logging.basicConfig(
    format='{"time":"%(asctime)s","level":"%(levelname)s","correlation_id":"' + _CORRELATION_ID + '","msg":"%(message)s"}',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def load_config(product):
    path = f"configs/{product}.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)


def check_table_exists(glue_client, database_name, table_name):
    """Verify the Iceberg table exists in Glue Catalog."""
    try:
        response = glue_client.get_table(
            DatabaseName=database_name,
            Name=table_name,
        )
        table = response["Table"]
        params = table.get("Parameters", {})
        is_iceberg = params.get("table_type") == "ICEBERG" or "iceberg" in str(params)
        return {
            "check": "table_exists",
            "passed": True,
            "is_iceberg": is_iceberg,
            "message": f"Table {database_name}.{table_name} exists (Iceberg: {is_iceberg})",
        }
    except glue_client.exceptions.EntityNotFoundException:
        return {
            "check": "table_exists",
            "passed": False,
            "message": f"Table {database_name}.{table_name} not found in Glue Catalog",
        }


def check_recent_data(glue_client, database_name, table_name, max_age_hours):
    """Verify the table has been updated recently."""
    try:
        response = glue_client.get_table(
            DatabaseName=database_name,
            Name=table_name,
        )
        table = response["Table"]
        update_time = table.get("UpdateTime")

        if not update_time:
            return {
                "check": "recent_data",
                "passed": False,
                "message": "Table has no UpdateTime metadata",
            }

        if update_time.tzinfo is None:
            update_time = update_time.replace(tzinfo=timezone.utc)

        age_hours = (datetime.now(timezone.utc) - update_time).total_seconds() / 3600

        passed = age_hours <= max_age_hours
        return {
            "check": "recent_data",
            "passed": passed,
            "age_hours": round(age_hours, 2),
            "max_age_hours": max_age_hours,
            "message": (
                f"Table updated {age_hours:.1f}h ago (max: {max_age_hours}h)"
                if passed
                else f"Table is stale: updated {age_hours:.1f}h ago (max: {max_age_hours}h)"
            ),
        }
    except Exception as e:
        return {
            "check": "recent_data",
            "passed": False,
            "message": f"Error checking data recency: {e}",
        }


def check_alarms(cloudwatch_client, product, env):
    """Verify all product-related CloudWatch alarms are in OK state."""
    alarm_prefix = f"adp-{product}"

    try:
        response = cloudwatch_client.describe_alarms(
            AlarmNamePrefix=alarm_prefix,
            StateValue="ALARM",
        )
        alarming = response.get("MetricAlarms", [])

        if alarming:
            alarm_names = [a["AlarmName"] for a in alarming]
            return {
                "check": "alarms_ok",
                "passed": False,
                "alarming_count": len(alarming),
                "alarm_names": alarm_names,
                "message": f"{len(alarming)} alarm(s) in ALARM state: {', '.join(alarm_names)}",
            }

        return {
            "check": "alarms_ok",
            "passed": True,
            "message": f"No alarms in ALARM state for prefix '{alarm_prefix}'",
        }
    except Exception as e:
        return {
            "check": "alarms_ok",
            "passed": False,
            "message": f"Error checking alarms: {e}",
        }


def main():
    parser = argparse.ArgumentParser(
        description="Post-deployment smoke test for analytical data products"
    )
    parser.add_argument("--product", required=True, help="Product name")
    parser.add_argument(
        "--env",
        required=True,
        choices=["dev", "staging", "prod"],
        help="Target environment",
    )
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=4.0,
        help="Maximum acceptable data age in hours (default: 4)",
    )
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    args = parser.parse_args()

    try:
        config = load_config(args.product)
    except FileNotFoundError:
        logger.error("Config file not found: configs/%s.yaml", args.product)
        sys.exit(1)

    domain = config.get("product", {}).get("domain", "default")
    database_name = f"{domain}_{args.product}_{args.env}"
    table_name = config.get("target", {}).get("table", args.product)

    glue_client = boto3.client("glue", region_name=args.region)
    cloudwatch_client = boto3.client("cloudwatch", region_name=args.region)

    logger.info("Running smoke tests for '%s' in %s", args.product, args.env)

    results = []

    # Check 1: Table exists
    result = check_table_exists(glue_client, database_name, table_name)
    results.append(result)
    log_fn = logger.info if result["passed"] else logger.error
    log_fn("%s: %s", "PASS" if result["passed"] else "FAIL", result["message"])

    # Check 2: Recent data
    result = check_recent_data(glue_client, database_name, table_name, args.max_age_hours)
    results.append(result)
    log_fn = logger.info if result["passed"] else logger.error
    log_fn("%s: %s", "PASS" if result["passed"] else "FAIL", result["message"])

    # Check 3: Alarms OK
    result = check_alarms(cloudwatch_client, args.product, args.env)
    results.append(result)
    log_fn = logger.info if result["passed"] else logger.error
    log_fn("%s: %s", "PASS" if result["passed"] else "FAIL", result["message"])

    all_passed = all(r["passed"] for r in results)
    passed_count = sum(1 for r in results if r["passed"])

    report = {
        "product": args.product,
        "environment": args.env,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "all_passed": all_passed,
        "summary": f"{passed_count}/{len(results)} checks passed",
        "results": results,
    }

    print(json.dumps(report, indent=2))

    if all_passed:
        logger.info("All smoke tests PASSED (%d/%d)", passed_count, len(results))
        sys.exit(0)
    else:
        logger.error(
            "Smoke tests FAILED (%d/%d passed)",
            passed_count,
            len(results),
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
