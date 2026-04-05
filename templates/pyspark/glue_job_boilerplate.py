"""
Generic AWS Glue PySpark ETL Job

A config-driven Glue job that reads a YAML pipeline config at runtime,
executes the SQL query from the config against Snowflake, and writes
the result to an Apache Iceberg table on S3 via the AWS Glue Catalog.

Multiple data products share this SAME code -- only the config differs.

Usage:
    Submitted as a Glue job script via the AWS Glue console or Terraform.
    Required arguments:
        --CONFIG_PATH   S3 URI or local path to the pipeline config YAML
        --ENV           Environment name (dev/staging/prod)
"""
import sys
import os
import logging
import uuid
import json
import re
import tempfile

import boto3
import yaml
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext

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
# Main execution
# ---------------------------------------------------------------------------
args = getResolvedOptions(sys.argv, ["JOB_NAME", "CONFIG_PATH", "ENV", "correlation_id"])
config_path = args["CONFIG_PATH"]
env = args["ENV"]
correlation_id = args.get("correlation_id") or str(uuid.uuid4())

# Set up logger
base_logger = logging.getLogger("adp_glue_etl")
if not base_logger.handlers:
    base_logger.setLevel(logging.INFO)
    handler_log = logging.StreamHandler()
    handler_log.setFormatter(_JsonFormatter())
    base_logger.addHandler(handler_log)
logger = logging.LoggerAdapter(base_logger, {"correlation_id": correlation_id})

# Initialize Glue job
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

logger.info(f"Starting Glue job {args['JOB_NAME']} in environment {env}")
logger.info(f"Correlation ID: {correlation_id}")
logger.info(f"Config path: {config_path}")

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
    target = config["target"]
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
            catalog = target["catalog"]
            database = target["database"]
            table_name = target["table"]
            # Validate identifiers to prevent SQL injection in REFRESH TABLE
            for ident in (catalog, database, table_name):
                if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', ident):
                    raise ValueError(f"Invalid identifier in target config: {ident!r}")
            full_table = f"{catalog}.{database}.{table_name}"
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

    # ------------------------------------------------------------------
    # Commit job on success
    # ------------------------------------------------------------------
    job.commit()
    logger.info("Glue job completed successfully.")

except Exception:
    logger.error("Glue job failed. See traceback below.", exc_info=True)
    raise
