"""
Generic AWS Lambda Python+Pandas ETL Handler

A config-driven Lambda function that reads a YAML pipeline config at
runtime, executes the SQL query from the config against Snowflake via
snowflake-connector-python, and writes the result to an Apache Iceberg
table via PyIceberg.

Multiple data products share this SAME code -- only the config differs.

Usage:
    Deployed as an AWS Lambda function. Invoked via EventBridge, Step
    Functions, or direct invocation.
    The config path is passed via event["config_path"] or the
    CONFIG_PATH environment variable.
"""
import os
import logging
import uuid
import json
import re
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
# Lambda handler
# ---------------------------------------------------------------------------
def handler(event, context):
    """
    Lambda ETL handler.

    Args:
        event: Invocation event dict. May contain:
            - config_path: S3 URI or local path to the pipeline config YAML
            - env: Environment name (dev/staging/prod)
            - correlation_id: Optional correlation ID for tracing
        context: Lambda context object.

    Returns:
        dict with statusCode (200 or 500) and JSON body.
    """
    correlation_id = event.get("correlation_id", str(uuid.uuid4()))
    config_path = event.get("config_path", os.environ.get("CONFIG_PATH"))
    env = event.get("env", os.environ.get("ENV", "prod"))
    aws_region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION"))

    # Set up logger
    base_logger = logging.getLogger("adp_lambda_etl")
    if not base_logger.handlers:
        base_logger.setLevel(logging.INFO)
        handler_log = logging.StreamHandler()
        handler_log.setFormatter(_JsonFormatter())
        base_logger.addHandler(handler_log)
    logger = logging.LoggerAdapter(base_logger, {"correlation_id": correlation_id})

    logger.info("Starting Lambda ETL job")
    logger.info(f"Correlation ID: {correlation_id}")
    logger.info(f"Config path: {config_path}, env: {env}")

    if not config_path:
        logger.error("No config_path provided in event or CONFIG_PATH env var")
        return {
            "statusCode": 400,
            "body": json.dumps({
                "status": "FAILED",
                "error": "config_path is required in event or CONFIG_PATH env var",
                "correlation_id": correlation_id,
            }),
        }

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

        logger.info("Lambda ETL job completed successfully.")
        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "SUCCESS",
                "correlation_id": correlation_id,
                "product": product_name,
                "rows_written": row_count,
            }),
        }

    except Exception as exc:
        logger.error("Lambda ETL job failed. See traceback below.", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "FAILED",
                "error": str(exc),
                "correlation_id": correlation_id,
            }),
        }
