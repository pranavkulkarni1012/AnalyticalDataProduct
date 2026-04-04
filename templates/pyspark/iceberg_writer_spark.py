"""
Iceberg Writer for PySpark (Spark writeTo API)
Template: iceberg_writer_spark.py

Provides the write_to_iceberg() function for PySpark-based engines
(Glue and EMR). Writes a Spark DataFrame to an Iceberg table using
the df.writeTo() API, supporting both overwritePartitions and append modes.

Used by both glue_job_boilerplate.py and emr_job_boilerplate.py.
"""
import logging


def write_to_iceberg(df, target, logger):
    """
    Write a Spark DataFrame to an Iceberg table.

    Uses the Spark writeTo API to write data to the specified Iceberg table.
    Supports both overwritePartitions (for incremental/overwrite loads) and
    append (for full/append loads) modes.

    Args:
        df: Spark DataFrame to write.
        target: Target config dict with catalog, database, table, and
                write_mode keys.
        logger: Logger instance with correlation ID.

    Raises:
        ValueError: If write_mode is not 'overwrite' or 'append'.
        Exception: If the Iceberg write operation fails.
    """
    catalog = target["catalog"]
    database = target["database"]
    table = target["table"]
    write_mode = target.get("write_mode", "overwrite")

    target_table = f"{catalog}.{database}.{table}"
    logger.info(f"Writing to Iceberg table: {target_table} (mode={write_mode})")

    if write_mode == "overwrite":
        df.writeTo(target_table).overwritePartitions()
    elif write_mode == "append":
        df.writeTo(target_table).append()
    else:
        raise ValueError(
            f"Unsupported write_mode '{write_mode}'. "
            "Expected 'overwrite' or 'append'."
        )

    logger.info(f"Successfully wrote to Iceberg table: {target_table}")
