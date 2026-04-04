#!/usr/bin/env python3
"""Poll a Step Function execution until it reaches a terminal state.

Usage:
    python scripts/wait_for_execution.py --product my_product --env dev
    python scripts/wait_for_execution.py --execution-arn arn:aws:states:... --timeout 600

Exit codes:
    0 - Execution succeeded
    1 - Execution failed, timed out, or an error occurred
"""

import argparse
import json
import logging
import sys
import time

import boto3

import uuid as _uuid

_CORRELATION_ID = str(_uuid.uuid4())

logging.basicConfig(
    format='{"time":"%(asctime)s","level":"%(levelname)s","correlation_id":"' + _CORRELATION_ID + '","msg":"%(message)s"}',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TERMINAL_STATES = {"SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"}


def find_latest_execution(sfn_client, product, env, region):
    """Find the most recent execution for a product's state machine."""
    account_id = boto3.client("sts").get_caller_identity()["Account"]

    # List state machines and find the matching one
    paginator = sfn_client.get_paginator("list_state_machines")
    target_prefix = f"adp-"
    target_suffix = f"-{product}-{env}"

    for page in paginator.paginate():
        for sm in page["stateMachines"]:
            if sm["name"].startswith(target_prefix) and sm["name"].endswith(target_suffix):
                # Get the latest execution
                executions = sfn_client.list_executions(
                    stateMachineArn=sm["stateMachineArn"],
                    maxResults=1,
                )
                if executions["executions"]:
                    return executions["executions"][0]["executionArn"]

    return None


def poll_execution(sfn_client, execution_arn, poll_interval, timeout):
    """Poll execution until terminal state or timeout."""
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        if elapsed >= timeout:
            logger.error(
                "Timeout after %ds waiting for execution: %s",
                timeout,
                execution_arn,
            )
            return "TIMED_OUT"

        response = sfn_client.describe_execution(executionArn=execution_arn)
        status = response["status"]

        if status in TERMINAL_STATES:
            return status

        logger.info(
            "Execution status: %s (elapsed: %ds / %ds)",
            status,
            int(elapsed),
            timeout,
        )
        time.sleep(poll_interval)


def main():
    parser = argparse.ArgumentParser(
        description="Poll a Step Function execution until completion"
    )
    parser.add_argument("--product", help="Product name (to auto-discover state machine)")
    parser.add_argument("--env", help="Environment (dev/staging/prod)")
    parser.add_argument("--execution-arn", help="Execution ARN (overrides auto-discovery)")
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=30,
        help="Poll interval in seconds (default: 30)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Timeout in seconds (default: 1800 = 30 minutes)",
    )
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    args = parser.parse_args()

    if not args.execution_arn and not (args.product and args.env):
        parser.error("Either --execution-arn or both --product and --env are required")

    sfn_client = boto3.client("stepfunctions", region_name=args.region)

    execution_arn = args.execution_arn
    if not execution_arn:
        logger.info("Discovering latest execution for %s in %s...", args.product, args.env)
        execution_arn = find_latest_execution(sfn_client, args.product, args.env, args.region)
        if not execution_arn:
            logger.error(
                "No execution found for product '%s' in env '%s'",
                args.product,
                args.env,
            )
            sys.exit(1)

    logger.info("Polling execution: %s", execution_arn)
    logger.info("Poll interval: %ds, Timeout: %ds", args.poll_interval, args.timeout)

    final_status = poll_execution(sfn_client, execution_arn, args.poll_interval, args.timeout)

    if final_status == "SUCCEEDED":
        logger.info("Execution SUCCEEDED: %s", execution_arn)
        sys.exit(0)
    else:
        logger.error("Execution %s: %s", final_status, execution_arn)
        sys.exit(1)


if __name__ == "__main__":
    main()
