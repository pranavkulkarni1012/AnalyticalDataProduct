"""
AWS Glue PySpark ETL Job Boilerplate
Template: glue_job_boilerplate.py

Provides the standard Glue job skeleton with GlueContext initialization,
structured logging with correlation IDs, and job bookmark support.

Generated code sections are marked with {{ generated_code }} placeholders.
The Pipeline Generator Agent fills these in during code generation.

Usage:
    Submitted as a Glue job script via the AWS Glue console or Terraform.
    Arguments --JOB_NAME and --ENV are resolved via getResolvedOptions.
"""
import sys
import os
import logging
import uuid
import json
from datetime import datetime

import boto3
from awsglue.transforms import *  # noqa: F401,F403
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext
from pyspark.sql import SparkSession
import pyspark.sql.functions as F


# ---------------------------------------------------------------------------
# Structured logging setup
# ---------------------------------------------------------------------------
product_name = "{{ product_name }}"
correlation_id = str(uuid.uuid4())

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
logger = logging.LoggerAdapter(base_logger, {"correlation_id": correlation_id})

# ---------------------------------------------------------------------------
# Glue / Spark initialization
# ---------------------------------------------------------------------------
args = getResolvedOptions(sys.argv, ["JOB_NAME", "ENV"])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)
env = args["ENV"]

logger.info(f"Starting Glue job {args['JOB_NAME']} in environment {env}")
logger.info(f"Correlation ID: {correlation_id}")

try:
    # -------------------------------------------------------------------
    # Proxy configuration (if required)
    # -------------------------------------------------------------------
    # {{ proxy_setup }}

    # -------------------------------------------------------------------
    # OAuth token retrieval from AWS Secrets Manager
    # -------------------------------------------------------------------
    secret_client = boto3.client("secretsmanager")
    try:
        secret_value = json.loads(
            secret_client.get_secret_value(
                SecretId="{{ secrets_manager_path }}"
            )["SecretString"]
        )
        oauth_token = secret_value["access_token"]
        logger.info("Successfully retrieved OAuth token from Secrets Manager")
    except Exception:
        logger.error(
            "Failed to retrieve OAuth token from Secrets Manager",
            exc_info=True,
        )
        raise

    # Snowflake connection options (Spark connector)
    sf_options_base = {
        "sfURL": "{{ snowflake_account }}.snowflakecomputing.com",
        "sfWarehouse": "{{ snowflake_warehouse }}",
        "sfRole": "{{ snowflake_role }}",
        "authenticator": "oauth",
        "token": oauth_token,
        # {{ proxy_options }}
    }

    # -------------------------------------------------------------------
    # Source reading
    # -------------------------------------------------------------------
    # {{ source_reading }}

    # -------------------------------------------------------------------
    # Joins
    # -------------------------------------------------------------------
    # {{ joins }}

    # -------------------------------------------------------------------
    # Column mappings and aggregations
    # -------------------------------------------------------------------
    # {{ column_mappings_and_aggregations }}

    # -------------------------------------------------------------------
    # Post-aggregation filters
    # -------------------------------------------------------------------
    # {{ filters }}

    # -------------------------------------------------------------------
    # Write to Iceberg target
    # -------------------------------------------------------------------
    # {{ iceberg_write }}

    # -------------------------------------------------------------------
    # Reconciliation checks
    # -------------------------------------------------------------------
    # {{ reconciliation }}

    # -------------------------------------------------------------------
    # Commit job on success
    # -------------------------------------------------------------------
    job.commit()
    logger.info("Job completed successfully.")

except Exception:
    logger.error("Job failed. See traceback below.", exc_info=True)
    raise
