"""
Snowflake Reader for PySpark (Spark Connector)
Template: snowflake_reader_spark.py

Provides utility functions for connecting to Snowflake via the Spark
Snowflake connector and executing arbitrary SQL queries. Used by the
generic Glue and EMR pipeline templates.

The SQL query comes from the pipeline config YAML at runtime -- this
module does NOT build queries from source metadata.

Used by both glue_job_boilerplate.py and emr_job_boilerplate.py.
"""
import os
import json
import logging
import re
from urllib.parse import urlparse

import boto3


# ---------------------------------------------------------------------------
# SQL safety validation
# ---------------------------------------------------------------------------
_DISALLOWED_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|COPY)\b",
    re.IGNORECASE,
)


def setup_proxy(proxy_config, logger):
    """
    Set proxy environment variables from the connection proxy config.

    Args:
        proxy_config: dict with http_proxy and/or https_proxy URLs.
        logger: Logger instance with correlation ID.
    """
    if not proxy_config:
        return

    for key in ("http_proxy", "https_proxy"):
        url = proxy_config.get(key)
        if url:
            os.environ[key] = url
            os.environ[key.upper()] = url

    logger.info("Proxy environment variables configured")


def get_oauth_token(account, logger):
    """
    Retrieve the Snowflake OAuth token from AWS Secrets Manager.

    Args:
        account: Full Snowflake account locator including region
                 (e.g., 'company-prod.us-east-1').
        logger: Logger instance with correlation ID.

    Returns:
        The OAuth access_token string.

    Raises:
        Exception: If the secret cannot be retrieved or parsed.
    """
    secret_path = f"adp/snowflake/{account}/oauth"
    secret_client = boto3.client("secretsmanager")
    try:
        secret_value = json.loads(
            secret_client.get_secret_value(SecretId=secret_path)[
                "SecretString"
            ]
        )
        oauth_token = secret_value["access_token"]
        logger.info("Successfully retrieved OAuth token from Secrets Manager")
        return oauth_token
    except Exception:
        logger.error(
            "Failed to retrieve OAuth token from Secrets Manager",
            exc_info=True,
        )
        raise


def build_sf_options(connection, oauth_token):
    """
    Build the Snowflake Spark connector options dict.

    Args:
        connection: Source connection config dict with account, warehouse,
                    role, and optional proxy settings.
        oauth_token: OAuth access_token string.

    Returns:
        dict of Snowflake Spark connector options.
    """
    options = {
        "sfURL": f"{connection['account']}.snowflakecomputing.com",
        "sfWarehouse": connection["warehouse"],
        "sfRole": connection["role"],
        "authenticator": "oauth",
        "token": oauth_token,
    }

    proxy_config = connection.get("proxy", {})
    proxy_url = proxy_config.get("https_proxy") or proxy_config.get(
        "http_proxy"
    )
    if proxy_url:
        parsed = urlparse(proxy_url)
        options["use_proxy"] = "true"
        if parsed.hostname:
            options["proxy_host"] = parsed.hostname
        if parsed.port is not None:
            options["proxy_port"] = str(parsed.port)

    return options


def run_query(spark, sf_options, query_sql, connection, logger):
    """
    Execute an arbitrary SQL query against Snowflake and return a Spark DataFrame.

    Validates the SQL for safety (SELECT-only) before execution as
    defense-in-depth.

    Args:
        spark: Active SparkSession.
        sf_options: Snowflake connection options dict from build_sf_options().
        query_sql: SQL query string to execute (must be SELECT or WITH).
        connection: Source connection config dict (used for database/schema
                    context if needed by the connector).
        logger: Logger instance with correlation ID.

    Returns:
        Spark DataFrame containing the query results.

    Raises:
        ValueError: If the SQL contains disallowed DML/DDL keywords.
    """
    stripped = query_sql.strip().rstrip(";").strip()
    if not stripped.upper().startswith(("SELECT", "WITH")):
        raise ValueError("Query SQL must start with SELECT or WITH (CTE).")
    if _DISALLOWED_SQL.search(stripped):
        raise ValueError(
            "Query SQL contains disallowed DML/DDL keywords. "
            "Only SELECT queries are permitted against Snowflake."
        )

    logger.info("Executing SQL query against Snowflake via Spark connector")

    query_options = {
        **sf_options,
        "query": stripped,
    }

    # Include database/schema context if available in the connection config
    if connection.get("database"):
        query_options["sfDatabase"] = connection["database"]
    if connection.get("schema"):
        query_options["sfSchema"] = connection["schema"]

    df = (
        spark.read.format("net.snowflake.spark.snowflake")
        .options(**query_options)
        .load()
    )

    logger.info("Snowflake query executed successfully via Spark connector")

    return df
