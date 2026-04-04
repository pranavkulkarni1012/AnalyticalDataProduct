"""
Iceberg Writer for Python/Pandas (PyIceberg Table API)
Template: iceberg_writer_pyiceberg.py

Provides the write_to_iceberg() function for Python-based engines
(Lambda and ECS). Converts a pandas DataFrame to PyArrow and writes
to an Iceberg table using the PyIceberg Table API, supporting both
overwrite and append modes.

Used by both lambda_handler.py and ecs_entrypoint.py.
"""
import os
import logging

import pyarrow as pa
from pyiceberg.catalog import load_catalog


def write_to_iceberg(df, target, logger, aws_region=None):
    """
    Write a pandas DataFrame to an Iceberg table via PyIceberg.

    Loads the Iceberg catalog (backed by AWS Glue), converts the pandas
    DataFrame to a PyArrow table, and writes using the specified mode.

    Args:
        df: pandas DataFrame to write.
        target: Target config dict with catalog, database, table, and
                write_mode keys.
        logger: Logger instance with correlation ID.
        aws_region: AWS region string. If None, reads from AWS_REGION
                    or AWS_DEFAULT_REGION environment variables.

    Raises:
        ValueError: If write_mode is not 'overwrite' or 'append'.
        Exception: If the Iceberg write operation fails.
    """
    catalog_name = target["catalog"]
    database = target["database"]
    table_name = target["table"]
    write_mode = target.get("write_mode", "overwrite")

    if aws_region is None:
        aws_region = os.environ.get(
            "AWS_REGION",
            os.environ.get("AWS_DEFAULT_REGION"),
        )

    if aws_region is None:
        raise ValueError(
            "AWS region is not set. Provide aws_region argument or set "
            "AWS_REGION / AWS_DEFAULT_REGION environment variable."
        )

    logger.info(
        f"Writing to Iceberg table: {database}.{table_name} "
        f"(mode={write_mode})"
    )

    catalog = load_catalog(
        catalog_name,
        **{
            "type": "glue",
            "client.region": aws_region,
        },
    )
    table = catalog.load_table(f"{database}.{table_name}")

    arrow_table = pa.Table.from_pandas(df)

    if write_mode == "overwrite":
        table.overwrite(arrow_table)
    elif write_mode == "append":
        table.append(arrow_table)
    else:
        raise ValueError(
            f"Unsupported write_mode '{write_mode}'. "
            "Expected 'overwrite' or 'append'."
        )

    logger.info(
        f"Successfully wrote to Iceberg table: {database}.{table_name}"
    )
