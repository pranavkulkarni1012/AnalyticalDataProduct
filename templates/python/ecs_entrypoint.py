"""
Generic AWS ECS Fargate Python+Pandas ETL Entrypoint

A config-driven ECS task that reads a YAML pipeline config at runtime,
executes the SQL query from the config against Snowflake via
snowflake-connector-python, and writes the result to an Apache Iceberg
table via PyIceberg.

Multiple data products share this SAME code -- only the config differs.

Usage:
    Runs as a Docker container on ECS Fargate. Entry point is main().
    Arguments:
        --config-path   S3 URI or local path to the pipeline config YAML
        --env           Environment name (dev/staging/prod)
"""
import os
import sys
import logging
import uuid
import json
import re
import signal
import argparse
import tempfile

import boto3
import yaml

from snowflake_reader_pandas import setup_proxy, get_oauth_token, build_conn_params, run_query
from iceberg_writer_pyiceberg import write_to_iceberg
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
# Graceful shutdown
# ---------------------------------------------------------------------------
_shutdown_requested = False


def _sigterm_handler(signum, frame):
    """Handle SIGTERM for graceful shutdown in Fargate."""
    global _shutdown_requested
    _shutdown_requested = True


signal.signal(signal.SIGTERM, _sigterm_handler)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
def parse_args():
    """Parse command-line arguments for the ECS job."""
    parser = argparse.ArgumentParser(description="Generic ECS ETL job")
    parser.add_argument(
        "--config-path",
        default=os.environ.get("CONFIG_PATH"),
        help="S3 URI or local path to the pipeline config YAML",
    )
    parser.add_argument(
        "--env",
        default=os.environ.get("ENV", "prod"),
        help="Environment (dev/staging/prod)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main():
    """Main entry point for the ECS ETL job."""
    args = parse_args()
    config_path = args.config_path
    env = args.env
    correlation_id = os.environ.get("CORRELATION_ID", str(uuid.uuid4()))
    aws_region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION"))

    # Set up logger
    base_logger = logging.getLogger("adp_ecs_etl")
    if not base_logger.handlers:
        base_logger.setLevel(logging.INFO)
        handler_log = logging.StreamHandler()
        handler_log.setFormatter(_JsonFormatter())
        base_logger.addHandler(handler_log)
    logger = logging.LoggerAdapter(base_logger, {"correlation_id": correlation_id})

    logger.info(f"Starting ECS ETL job in environment {env}")
    logger.info(f"Correlation ID: {correlation_id}")
    logger.info(f"Config path: {config_path}")

    if not config_path:
        logger.error("No config_path provided via --config-path or CONFIG_PATH env var")
        sys.exit(1)

    try:
        # ------------------------------------------------------------------
        # Load pipeline config
        # ------------------------------------------------------------------
        config = _load_config(config_path)
        product_name = config.get("product", {}).get("name", "unknown")
        logger.info(f"Loaded config for product: {product_name}")

        # ------------------------------------------------------------------
        # Check for shutdown before heavy processing
        # ------------------------------------------------------------------
        if _shutdown_requested:
            logger.warning("Shutdown requested before query execution, exiting")
            sys.exit(0)

        # ------------------------------------------------------------------
        # Validate SQL
        # ------------------------------------------------------------------
        query_sql = config["query"]["sql"]
        _validate_sql(query_sql)
        logger.info("SQL validation passed")

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
        # Build Snowflake connection parameters
        # ------------------------------------------------------------------
        conn_params = build_conn_params(connection, oauth_token)

        # ------------------------------------------------------------------
        # Execute query against Snowflake
        # ------------------------------------------------------------------
        df = run_query(conn_params, query_sql, logger)
        row_count = len(df)
        logger.info(f"Query returned {row_count} rows")

        # ------------------------------------------------------------------
        # Check for shutdown before writing
        # ------------------------------------------------------------------
        if _shutdown_requested:
            logger.warning("Shutdown requested before Iceberg write, exiting")
            sys.exit(0)

        # ------------------------------------------------------------------
        # Write to Iceberg target
        # ------------------------------------------------------------------
        target = config["target"]
        write_to_iceberg(df, target, logger, aws_region=aws_region)

        # ------------------------------------------------------------------
        # Reconciliation checks
        # ------------------------------------------------------------------
        recon_config = config.get("reconciliation", {})
        recon_rules = recon_config.get("rules", [])
        if recon_rules:
            def _sf_executor(sql_expr):
                """Execute a scalar SQL expression against Snowflake."""
                recon_df = run_query(conn_params, sql_expr, logger)
                return recon_df.iloc[0, 0]

            recon_result = run_reconciliation(
                rules=recon_rules,
                logger=logger,
                correlation_id=correlation_id,
                source_executor=_sf_executor,
                target_df=df,
            )
            logger.info(f"Reconciliation result: {json.dumps(recon_result)}")
            if recon_result["overall_status"] == "FAIL":
                logger.warning("Reconciliation FAILED -- check rule results for details")
        else:
            logger.info("No reconciliation rules configured, skipping")

        logger.info("ECS ETL job completed successfully.")
        sys.exit(0)

    except Exception:
        logger.error("ECS ETL job failed. See traceback below.", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
