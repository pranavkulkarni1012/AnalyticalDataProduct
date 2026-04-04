"""
AWS EMR PySpark ETL Job Boilerplate
Template: emr_job_boilerplate.py

Provides the standard EMR job skeleton with plain SparkSession (no GlueContext),
argparse for CLI arguments, structured logging with correlation IDs, and
proper SparkSession lifecycle management.

Generated code sections are marked with {{ generated_code }} placeholders.
The Pipeline Generator Agent fills these in during code generation.

Usage:
    Submitted as an EMR step (EC2) or EMR Serverless job run.
    Arguments: --env <environment> [--job-name <name>]
"""
import sys
import os
import logging
import uuid
import json
import argparse
from datetime import datetime

import boto3
from pyspark.sql import SparkSession
import pyspark.sql.functions as F


product_name = "{{ product_name }}"


def parse_args():
    """Parse command-line arguments for the EMR job."""
    parser = argparse.ArgumentParser(
        description=f"EMR ETL job for {product_name}"
    )
    parser.add_argument(
        "--env",
        required=True,
        help="Environment (dev/staging/prod)",
    )
    parser.add_argument(
        "--job-name",
        default=f"adp-{{{{ product_domain }}}}-{product_name}-etl-prod",
        help="Job name for logging (defaults to config-derived name)",
    )
    args, _ = parser.parse_known_args()  # ignore EMR Serverless framework args
    return args


def main():
    """Main entry point for the EMR ETL job."""
    args = parse_args()
    correlation_id = str(uuid.uuid4())

    # -------------------------------------------------------------------
    # Structured logging setup
    # -------------------------------------------------------------------
    base_logger = logging.getLogger(f"{product_name}_etl")
    if not base_logger.handlers:
        base_logger.setLevel(logging.INFO)
        handler_log = logging.StreamHandler()
        handler_log.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(correlation_id)s | %(message)s"
            )
        )
        base_logger.addHandler(handler_log)
    logger = logging.LoggerAdapter(
        base_logger, {"correlation_id": correlation_id}
    )

    # -------------------------------------------------------------------
    # SparkSession with Iceberg catalog
    # -------------------------------------------------------------------
    catalog_name = "{{ target_catalog }}"
    spark = None
    try:
        spark = (
            SparkSession.builder
            .appName(args.job_name)
            .config(
                f"spark.sql.catalog.{catalog_name}",
                "org.apache.iceberg.spark.SparkCatalog",
            )
            .config(
                f"spark.sql.catalog.{catalog_name}.warehouse",
                "{{ warehouse_s3_path }}",
            )
            .config(
                f"spark.sql.catalog.{catalog_name}.catalog-impl",
                "org.apache.iceberg.aws.glue.GlueCatalog",
            )
            .config(
                f"spark.sql.catalog.{catalog_name}.io-impl",
                "org.apache.iceberg.aws.s3.S3FileIO",
            )
            .getOrCreate()
        )

        logger.info(f"Starting job {args.job_name} in environment {args.env}")
        logger.info(f"Correlation ID: {correlation_id}")

        # ---------------------------------------------------------------
        # Proxy configuration (if required)
        # ---------------------------------------------------------------
        # {{ proxy_setup }}

        # ---------------------------------------------------------------
        # OAuth token retrieval from AWS Secrets Manager
        # ---------------------------------------------------------------
        secret_client = boto3.client("secretsmanager")
        try:
            secret_value = json.loads(
                secret_client.get_secret_value(
                    SecretId="{{ secrets_manager_path }}"
                )["SecretString"]
            )
            oauth_token = secret_value["access_token"]
            logger.info(
                "Successfully retrieved OAuth token from Secrets Manager"
            )
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

        # ---------------------------------------------------------------
        # Source reading
        # ---------------------------------------------------------------
        # {{ source_reading }}

        # ---------------------------------------------------------------
        # Joins
        # ---------------------------------------------------------------
        # {{ joins }}

        # ---------------------------------------------------------------
        # Column mappings and aggregations
        # ---------------------------------------------------------------
        # {{ column_mappings_and_aggregations }}

        # ---------------------------------------------------------------
        # Post-aggregation filters
        # ---------------------------------------------------------------
        # {{ filters }}

        # ---------------------------------------------------------------
        # Write to Iceberg target
        # ---------------------------------------------------------------
        # {{ iceberg_write }}

        # ---------------------------------------------------------------
        # Reconciliation checks
        # ---------------------------------------------------------------
        # {{ reconciliation }}

        logger.info("Job completed successfully.")

    except Exception:
        logger.error("Job failed. See traceback below.", exc_info=True)
        raise
    finally:
        if spark:
            try:
                spark.stop()
            except Exception:
                logger.warning("Error stopping SparkSession", exc_info=True)


if __name__ == "__main__":
    main()
