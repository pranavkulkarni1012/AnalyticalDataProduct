"""
Snowflake Reader for Python/Pandas (DBAPI Connector)
Template: snowflake_reader_pandas.py

Provides utility functions for connecting to Snowflake via
snowflake-connector-python and executing arbitrary SQL queries. Used by
the generic Lambda and ECS pipeline templates.

The SQL query comes from the pipeline config YAML at runtime -- this
module does NOT build queries from source metadata.

Used by both lambda_handler.py and ecs_entrypoint.py.
"""
import os
import json
import logging
import re
from urllib.parse import urlparse

import boto3
import snowflake.connector
import pandas as pd


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


def build_conn_params(connection, oauth_token):
    """
    Build Snowflake DBAPI connection parameters.

    Args:
        connection: Source connection config dict with account, warehouse,
                    role, and optional proxy settings.
        oauth_token: OAuth access_token string.

    Returns:
        dict of snowflake.connector.connect() parameters.
    """
    params = {
        "account": connection["account"],
        "authenticator": "oauth",
        "token": oauth_token,
        "warehouse": connection["warehouse"],
        "role": connection["role"],
    }

    proxy_config = connection.get("proxy", {})
    proxy_url = proxy_config.get("https_proxy") or proxy_config.get(
        "http_proxy"
    )
    if proxy_url:
        parsed = urlparse(proxy_url)
        if parsed.hostname:
            params["proxy_host"] = parsed.hostname
        if parsed.port is not None:
            params["proxy_port"] = parsed.port

    return params


def run_query(conn_params, query_sql, logger):
    """
    Execute an arbitrary SQL query against Snowflake and return a pandas DataFrame.

    Validates the SQL for safety (SELECT-only) before execution as
    defense-in-depth.

    Args:
        conn_params: Snowflake connection parameters from build_conn_params().
        query_sql: SQL query string to execute (must be SELECT or WITH).
        logger: Logger instance with correlation ID.

    Returns:
        pandas DataFrame containing the query results.

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

    logger.info("Executing SQL query against Snowflake via DBAPI connector")

    with snowflake.connector.connect(**conn_params) as conn:
        with conn.cursor() as cursor:
            cursor.execute(stripped)
            df = cursor.fetch_pandas_all()

    row_count = len(df)
    logger.info(f"Snowflake query returned {row_count} rows")

    return df
