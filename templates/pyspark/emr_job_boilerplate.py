"""
Generic AWS EMR PySpark ETL Job

A config-driven EMR job that reads a YAML pipeline config at runtime,
executes the SQL query from the config against Snowflake, and writes
the result to an Apache Iceberg table on S3 via the AWS Glue Catalog.

Multiple data products share this SAME code -- only the config differs.

Usage:
    Submitted as an EMR step (EC2) or EMR Serverless job run.
    Arguments:
        --config-path   S3 URI or local path to the pipeline config YAML
        --env           Environment name (dev/staging/prod)
"""
import sys
import os
import logging
import uuid
import json
import re
import argparse
import tempfile

import boto3
import yaml
from pyspark.sql import SparkSession

from snowflake_reader_spark import setup_proxy, get_oauth_token, build_sf_options, run_query
from iceberg_writer_spark import write_to_iceberg
from reconciliation import run_reconciliation


# ---------------------------------------------------------------------------
# SQL safety validation
# ---------------------------------------------------------------------------
_DISALLOWED_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|COPY)\b",
    re.IGNORECASE,
)


def _validate_sql(sql):
    """Validate that the SQL is a SELECT-only statement (defense-in-depth)."""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped.upper().startswith(("SELECT", "WITH")):
        raise ValueError("Query SQL must start with SELECT or WITH (CTE).")
    if _DISALLOWED_SQL.search(stripped):
        raise ValueError(
            "Query SQL contains disallowed DML/DDL keywords. "
            "Only SELECT queries are permitted against Snowflake."
        )


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------
def _load_config(config_path):
    """Load a YAML config from an S3 URI or local file path."""
    if config_path.startswith("s3://"):
        s3 = boto3.client("s3")
        bucket, key = config_path.replace("s3://", "").split("/", 1)
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as tmp:
            s3.download_file(bucket, key, tmp.name)
            tmp_path = tmp.name
        with open(tmp_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        os.unlink(tmp_path)
    else:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    return config


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------
class _JsonFormatter(logging.Formatter):
    """JSON log formatter with correlation ID support."""

    def format(self, record):
        return json.dumps({
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "correlation_id": record.__dict__.get("correlation_id", ""),
            "msg": record.getMessage(),
        })


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
def parse_args():
    """Parse command-line arguments for the EMR job."""
    parser = argparse.ArgumentParser(description="Generic EMR ETL job")
    parser.add_argument(
        "--config-path",
        required=True,
        help="S3 URI or local path to the pipeline config YAML",
    )
    parser.add_argument(
        "--env",
        required=True,
        help="Environment (dev/staging/prod)",
    )
    parser.add_argument(
        "--correlation-id",
        required=False,
        default=None,
        help="Correlation ID from Step Function execution (auto-generated if omitted)",
    )
    args, _ = parser.parse_known_args()
    return args


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main():
    """Main entry point for the EMR ETL job."""
    args = parse_args()
    config_path = args.config_path
    env = args.env
    correlation_id = args.correlation_id or str(uuid.uuid4())

    # Set up logger
    base_logger = logging.getLogger("adp_emr_etl")
    if not base_logger.handlers:
        base_logger.setLevel(logging.INFO)
        handler_log = logging.StreamHandler()
        handler_log.setFormatter(_JsonFormatter())
        base_logger.addHandler(handler_log)
    logger = logging.LoggerAdapter(base_logger, {"correlation_id": correlation_id})

    spark = None
    try:
        # ------------------------------------------------------------------
        # Load pipeline config
        # ------------------------------------------------------------------
        config = _load_config(config_path)
        product_name = config.get("product", {}).get("name", "unknown")
        logger.info(f"Loaded config for product: {product_name}")

        # ------------------------------------------------------------------
        # Validate SQL
        # ------------------------------------------------------------------
        query_sql = config["query"]["sql"]
        _validate_sql(query_sql)
        logger.info("SQL validation passed")

        # ------------------------------------------------------------------
        # Build SparkSession with Iceberg catalog
        # ------------------------------------------------------------------
        target = config["target"]
        catalog_name = target.get("catalog", "glue_catalog")

        spark = (
            SparkSession.builder
            .appName(f"adp-{product_name}-{env}")
            .config(
                f"spark.sql.catalog.{catalog_name}",
                "org.apache.iceberg.spark.SparkCatalog",
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

        logger.info(f"Starting EMR job for {product_name} in environment {env}")
        logger.info(f"Correlation ID: {correlation_id}")
        logger.info(f"Config path: {config_path}")

        # ------------------------------------------------------------------
        # Proxy configuration
        # ------------------------------------------------------------------
        connection = config["source"]["connection"]
        proxy_config = connection.get("proxy")
        if proxy_config:
            setup_proxy(proxy_config, logger)

        # ------------------------------------------------------------------
        # OAuth token retrieval from AWS Secrets Manager
        # ------------------------------------------------------------------
        account = connection["account"]
        oauth_token = get_oauth_token(account, logger)

        # ------------------------------------------------------------------
        # Build Snowflake Spark connector options
        # ------------------------------------------------------------------
        sf_options = build_sf_options(connection, oauth_token)

        # ------------------------------------------------------------------
        # Execute query against Snowflake
        # ------------------------------------------------------------------
        df = run_query(spark, sf_options, query_sql, connection, logger)
        row_count = df.count()
        logger.info(f"Query returned {row_count} rows")

        # ------------------------------------------------------------------
        # Write to Iceberg target
        # ------------------------------------------------------------------
        write_to_iceberg(df, target, logger)

        # ------------------------------------------------------------------
        # Reconciliation checks
        # ------------------------------------------------------------------
        recon_config = config.get("reconciliation", {})
        recon_rules = recon_config.get("rules", [])
        if recon_rules:
            def _sf_executor(sql_expr):
                """Execute a scalar SQL expression against Snowflake."""
                recon_df = run_query(spark, sf_options, sql_expr, connection, logger)
                return recon_df.collect()[0][0]

            def _iceberg_executor(sql_expr):
                """Execute a scalar SQL expression against the Iceberg table."""
                # Validate identifiers to prevent SQL injection in REFRESH TABLE
                for ident in (catalog_name, target['database'], target['table']):
                    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', ident):
                        raise ValueError(f"Invalid identifier in target config: {ident!r}")
                full_table = f"{catalog_name}.{target['database']}.{target['table']}"
                spark.sql(f"REFRESH TABLE {full_table}")
                result_df = spark.sql(sql_expr)
                return result_df.collect()[0][0]

            recon_result = run_reconciliation(
                rules=recon_rules,
                logger=logger,
                correlation_id=correlation_id,
                source_executor=_sf_executor,
                target_executor=_iceberg_executor,
            )
            logger.info(f"Reconciliation result: {json.dumps(recon_result)}")
            if recon_result["overall_status"] == "FAIL":
                logger.warning("Reconciliation FAILED -- check rule results for details")
        else:
            logger.info("No reconciliation rules configured, skipping")

        logger.info("EMR job completed successfully.")

    except Exception:
        logger.error("EMR job failed. See traceback below.", exc_info=True)
        raise
    finally:
        if spark:
            try:
                spark.stop()
            except Exception:
                logger.warning("Error stopping SparkSession", exc_info=True)


if __name__ == "__main__":
    main()
