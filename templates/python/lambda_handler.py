"""
AWS Lambda Python+Pandas ETL Handler
Template: lambda_handler.py

Provides the standard Lambda handler skeleton with structured JSON logging,
correlation ID per invocation, and proper error handling with Lambda
response codes.

Generated code sections are marked with {{ generated_code }} placeholders.
The Pipeline Generator Agent fills these in during code generation.

Usage:
    Deployed as an AWS Lambda function. Invoked via EventBridge, Step
    Functions, or direct invocation.
"""
import os
import logging
import uuid
import json
from datetime import datetime

import boto3
import snowflake.connector
import pandas as pd
from pyiceberg.catalog import load_catalog
import pyarrow as pa


product_name = "{{ product_name }}"


def handler(event, context):
    """
    Lambda ETL handler.

    Args:
        event: Invocation event dict. May contain 'env' key.
        context: Lambda context object.

    Returns:
        dict with statusCode (200 or 500) and JSON body.
    """
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

    logger.info("Starting Lambda ETL job")
    logger.info(f"Correlation ID: {correlation_id}")

    env = event.get("env", os.environ.get("ENV", "prod"))

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
        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "SUCCESS",
                "correlation_id": correlation_id,
            }),
        }

    except Exception:
        logger.error("Job failed. See traceback below.", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "FAILED",
                "error": "ETL job failed. Check CloudWatch logs for details.",
                "correlation_id": correlation_id,
            }),
        }
