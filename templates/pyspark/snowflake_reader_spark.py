"""
Snowflake Reader for PySpark (Spark Connector)
Template: snowflake_reader_spark.py

Provides the read_from_snowflake() function for PySpark-based engines
(Glue and EMR). Retrieves an OAuth token from AWS Secrets Manager, sets
proxy environment variables for corporate networks, and reads data via
the Spark Snowflake connector (net.snowflake.spark.snowflake).

Used by both glue_job_boilerplate.py and emr_job_boilerplate.py.
"""
import os
import json
import logging
import re
from urllib.parse import urlparse

import boto3


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


def _quote_identifier(name):
    """Quote a SQL identifier with double-quotes to prevent injection."""
    return '"' + name.replace('"', '""') + '"'


def build_source_query(source):
    """
    Build a SQL SELECT query from the source configuration.

    Uses double-quoted identifiers to prevent SQL injection.

    Args:
        source: Source config dict with database, schema, table, columns,
                and filters.

    Returns:
        SQL query string.
    """
    fqn = (
        f"{_quote_identifier(source['database'])}."
        f"{_quote_identifier(source['schema'])}."
        f"{_quote_identifier(source['table'])}"
    )

    columns = source.get("columns", "*")
    if isinstance(columns, list) and columns:
        col_list = ", ".join(_quote_identifier(c) for c in columns)
    else:
        col_list = "*"

    query = f"SELECT {col_list} FROM {fqn}"

    # Filters come from the validated pipeline config YAML (not user input).
    # They are pre-validated by /validate-config against the JSON Schema.
    # We apply basic sanity checks here as defense-in-depth.
    _DISALLOWED_SQL = re.compile(
        r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|TRUNCATE|CREATE)\b",
        re.IGNORECASE,
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


def read_from_snowflake(spark, sf_options, source, logger):
    """
    Read a Snowflake source into a Spark DataFrame.

    Args:
        spark: Active SparkSession.
        sf_options: Base Snowflake connection options dict from
                    build_sf_options().
        source: Source config dict with database, schema, table, columns,
                and filters.
        logger: Logger instance with correlation ID.

    Returns:
        Spark DataFrame containing the source data.
    """
    query = build_source_query(source)
    source_name = source["name"]
    logger.info(f"Reading source '{source_name}' from Snowflake")

    per_source_options = {
        **sf_options,
        "sfDatabase": source["database"],
        "sfSchema": source["schema"],
        "query": query,
    }

    df = (
        spark.read.format("net.snowflake.spark.snowflake")
        .options(**per_source_options)
        .load()
    )

    row_count = df.count()
    logger.info(f"Source '{source_name}': {row_count} rows read")

    return df
