"""
Snowflake Reader for Python/Pandas (DBAPI Connector)
Template: snowflake_reader_pandas.py

Provides the read_from_snowflake() function for Python-based engines
(Lambda and ECS). Retrieves an OAuth token from AWS Secrets Manager, sets
proxy environment variables for corporate networks, and reads data via
snowflake-connector-python with cursor.fetch_pandas_all().

Used by both lambda_handler.py and ecs_entrypoint.py.
"""
import os
import json
import logging
from urllib.parse import urlparse

import boto3
import snowflake.connector
import pandas as pd


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


def build_source_query(source):
    """
    Build a SQL SELECT query from the source configuration.

    Uses fully-qualified table names with double-quoted identifiers
    to prevent SQL injection.

    Args:
        source: Source config dict with database, schema, table, columns,
                and filters.

    Returns:
        SQL query string.
    """
    def quote_identifier(name):
        return '"' + name.replace('"', '""') + '"'

    fqn = (
        f"{quote_identifier(source['database'])}."
        f"{quote_identifier(source['schema'])}."
        f"{quote_identifier(source['table'])}"
    )

    columns = source.get("columns", "*")
    if isinstance(columns, list) and columns:
        col_list = ", ".join(quote_identifier(c) for c in columns)
    else:
        col_list = "*"

    query = f"SELECT {col_list} FROM {fqn}"

    # Filters come from the validated pipeline config YAML (not user input).
    # They are pre-validated by /validate-config against the JSON Schema.
    # We apply basic sanity checks here as defense-in-depth.
    import re as _re
    _DISALLOWED_SQL = _re.compile(
        r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|TRUNCATE|CREATE)\b",
        _re.IGNORECASE,
    )
    filters = source.get("filters", [])
    safe_filters = []
    for f in filters:
        if _DISALLOWED_SQL.search(f):
            raise ValueError(f"Filter contains disallowed SQL keyword: {f}")
        safe_filters.append(f)
    if safe_filters:
        where_clause = " AND ".join(safe_filters)
        query += f" WHERE {where_clause}"

    return query


def read_from_snowflake(conn_params, source, logger):
    """
    Read a Snowflake source into a pandas DataFrame.

    Uses context managers for safe connection cleanup and
    cursor.fetch_pandas_all() for efficient reads.

    Args:
        conn_params: Base connection parameters from build_conn_params().
        source: Source config dict with database, schema, table, columns,
                and filters.
        logger: Logger instance with correlation ID.

    Returns:
        pandas DataFrame containing the source data.
    """
    query = build_source_query(source)
    source_name = source["name"]
    logger.info(f"Reading source '{source_name}' from Snowflake")

    per_source_params = {
        **conn_params,
        "database": source["database"],
        "schema": source["schema"],
    }

    with snowflake.connector.connect(**per_source_params) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            df = cursor.fetch_pandas_all()

    row_count = len(df)
    logger.info(f"Source '{source_name}': {row_count} rows read")

    return df
