"""
AWS ECS Fargate Python+Pandas ETL Entrypoint
Template: ecs_entrypoint.py

Provides the standard ECS entrypoint skeleton with argparse CLI arguments,
structured JSON logging, correlation ID per invocation, and graceful
shutdown handling for Fargate containers.

Generated code sections are marked with {{ generated_code }} placeholders.
The Pipeline Generator Agent fills these in during code generation.

Usage:
    Runs as a Docker container on ECS Fargate. Entry point is main().
    Arguments: --env <environment> [--job-name <name>]
"""
import os
import sys
import logging
import uuid
import json
import signal
import argparse
from datetime import datetime

import boto3
import snowflake.connector
import pandas as pd
from pyiceberg.catalog import load_catalog
import pyarrow as pa


product_name = "{{ product_name }}"

# Graceful shutdown flag for SIGTERM handling
_shutdown_requested = False


def _sigterm_handler(signum, frame):
    """Handle SIGTERM for graceful shutdown in Fargate."""
    global _shutdown_requested
    _shutdown_requested = True


signal.signal(signal.SIGTERM, _sigterm_handler)


def parse_args():
    """Parse command-line arguments for the ECS job."""
    parser = argparse.ArgumentParser(
        description=f"ECS ETL job for {product_name}"
    )
    parser.add_argument(
        "--env",
        default=os.environ.get("ENV", "prod"),
        help="Environment (dev/staging/prod)",
    )
    parser.add_argument(
        "--job-name",
        default=f"adp-{{{{ product_domain }}}}-{product_name}-etl-prod",
        help="Job name for logging",
    )
    return parser.parse_args()


def main():
    """Main entry point for the ECS ETL job."""
    args = parse_args()
    correlation_id = str(uuid.uuid4())

    # -------------------------------------------------------------------
    # Structured logging setup
    # -------------------------------------------------------------------
    class _JsonFormatter(logging.Formatter):
        def format(self, record):
            return json.dumps({
                "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                "level": record.levelname,
                "correlation_id": record.__dict__.get("correlation_id", ""),
                "msg": record.getMessage(),
            })

    base_logger = logging.getLogger(f"{product_name}_etl")
    if not base_logger.handlers:
        base_logger.setLevel(logging.INFO)
        handler_log = logging.StreamHandler()
        handler_log.setFormatter(_JsonFormatter())
        base_logger.addHandler(handler_log)
    logger = logging.LoggerAdapter(
        base_logger, {"correlation_id": correlation_id}
    )

    logger.info(f"Starting ECS job {args.job_name} in environment {args.env}")
    logger.info(f"Correlation ID: {correlation_id}")

    try:
        # ---------------------------------------------------------------
        # Proxy configuration (if required)
        # ---------------------------------------------------------------
        # {{ proxy_setup }}

        # ---------------------------------------------------------------
        # OAuth token retrieval from AWS Secrets Manager
        # ---------------------------------------------------------------
        # {{ oauth_retrieval }}

        # ---------------------------------------------------------------
        # Source reading (Snowflake via DBAPI + pandas)
        # ---------------------------------------------------------------
        # {{ source_reading }}

        # ---------------------------------------------------------------
        # Joins (pandas.merge)
        # ---------------------------------------------------------------
        # {{ joins }}

        # ---------------------------------------------------------------
        # Column mappings and aggregations (pandas.groupby().agg())
        # ---------------------------------------------------------------
        # {{ column_mappings_and_aggregations }}

        # ---------------------------------------------------------------
        # Post-aggregation filters
        # ---------------------------------------------------------------
        # {{ filters }}

        # ---------------------------------------------------------------
        # Write to Iceberg target (PyIceberg)
        # ---------------------------------------------------------------
        # {{ iceberg_write }}

        # ---------------------------------------------------------------
        # Reconciliation (synchronous Lambda invocation)
        # ---------------------------------------------------------------
        # {{ reconciliation }}

        logger.info("Job completed successfully.")
        sys.exit(0)

    except Exception:
        logger.error("Job failed. See traceback below.", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
