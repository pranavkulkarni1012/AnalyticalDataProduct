"""
Data Quality Check Template
Template: data_quality.py

Provides the run_data_quality_checks() function that validates a target
dataset after ETL completes. Works with both Spark DataFrames and Pandas
DataFrames using duck-typed adapters.

Supports check types: not_null, unique, range, regex, custom.
Returns structured results with per-check pass/fail and violation counts,
suitable for JSON serialization (feeds into 06-validation-report.json).

Used across all compute engines (Glue, EMR, Lambda, ECS).
"""
import logging
import uuid
import re
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# DataFrame adapters -- duck-typed support for Spark and Pandas
# ---------------------------------------------------------------------------

def _is_spark_dataframe(df):
    """Check if a DataFrame is a Spark DataFrame without importing PySpark."""
    type_name = type(df).__module__ + "." + type(df).__qualname__
    return "pyspark" in type_name


def _get_row_count(df):
    """Get total row count from either Spark or Pandas DataFrame."""
    if _is_spark_dataframe(df):
        return df.count()
    return len(df)


def _get_null_count(df, column):
    """Get null/NaN count for a column."""
    if _is_spark_dataframe(df):
        from pyspark.sql.functions import col, isnull, isnan
        from pyspark.sql.types import DoubleType, FloatType
        field = next(
            (f for f in df.schema.fields if f.name == column), None
        )
        if field and isinstance(field.dataType, (DoubleType, FloatType)):
            return df.filter(
                isnull(col(column)) | isnan(col(column))
            ).count()
        return df.filter(isnull(col(column))).count()
    return int(df[column].isna().sum())


def _get_duplicate_count(df, column, total_rows=None):
    """Get count of duplicate values in a column."""
    if _is_spark_dataframe(df):
        total = total_rows if total_rows is not None else df.count()
        distinct = df.select(column).distinct().count()
        return total - distinct
    total = total_rows if total_rows is not None else len(df)
    distinct = df[column].nunique(dropna=False)
    return total - distinct


def _get_out_of_range_count(df, column, min_val=None, max_val=None):
    """Get count of values outside the specified range."""
    if _is_spark_dataframe(df):
        from pyspark.sql.functions import col
        condition = None
        if min_val is not None:
            condition = col(column) < min_val
        if max_val is not None:
            max_cond = col(column) > max_val
            condition = (condition | max_cond) if condition else max_cond
        if condition is None:
            return 0
        return df.filter(condition).count()

    violations = 0
    if min_val is not None:
        violations += int((df[column] < min_val).sum())
    if max_val is not None:
        violations += int((df[column] > max_val).sum())
    return violations


def _get_regex_violation_count(df, column, pattern):
    """Get count of values that do not match the regex pattern (full string)."""
    if _is_spark_dataframe(df):
        from pyspark.sql.functions import col
        anchored = f"^(?:{pattern})$"
        return df.filter(~col(column).rlike(anchored)).count()
    compiled = re.compile(pattern)
    non_null = df[column].dropna()
    violations = non_null.apply(
        lambda x: not bool(compiled.fullmatch(str(x)))
    )
    return int(violations.sum())


# ---------------------------------------------------------------------------
# Data quality engine
# ---------------------------------------------------------------------------

def run_data_quality_checks(df, checks, logger, correlation_id=None):
    """
    Run data quality checks on a DataFrame.

    Executes each check independently (one check's failure does not block
    others) and returns a structured report suitable for JSON serialization.

    Args:
        df: Target DataFrame (Spark or Pandas) to validate.
        checks: List of check dicts from the pipeline config.
            Each check has: name, type, column, and optional parameters.
        logger: Logger instance with correlation ID.
        correlation_id: Optional correlation ID for tracing.

    Returns:
        dict with:
            - overall_status: "PASS" or "FAIL"
            - run_timestamp: ISO-8601 timestamp
            - correlation_id: Correlation ID string
            - total_rows: Total row count in the DataFrame
            - checks: List of per-check result dicts
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    overall_status = "PASS"
    results = []
    total_rows = _get_row_count(df)

    logger.info(
        f"Starting data quality checks: {len(checks)} checks on "
        f"{total_rows} rows (correlation_id={correlation_id})"
    )

    for check in checks:
        check_name = check["name"]
        check_type = check["type"]
        column = check.get("column")
        parameters = check.get("parameters", {})

        try:
            if check_type == "not_null":
                result = _check_not_null(df, check_name, column, total_rows)
            elif check_type == "unique":
                result = _check_unique(df, check_name, column, total_rows)
            elif check_type == "range":
                result = _check_range(
                    df, check_name, column, parameters, total_rows
                )
            elif check_type == "regex":
                result = _check_regex(
                    df, check_name, column, parameters, total_rows
                )
            elif check_type == "custom":
                result = _check_custom(
                    df, check_name, column, parameters, total_rows
                )
            else:
                logger.warning(
                    f"Check '{check_name}': unknown type '{check_type}', "
                    "skipping"
                )
                result = {
                    "check": check_name,
                    "type": check_type,
                    "column": column,
                    "status": "SKIP",
                    "message": f"Unknown check type: {check_type}",
                }
                results.append(result)
                continue

        except Exception:
            logger.error(
                f"Check '{check_name}' failed with error", exc_info=True
            )
            result = {
                "check": check_name,
                "type": check_type,
                "column": column,
                "status": "ERROR",
                "message": (
                    "Check evaluation failed. "
                    "See pipeline logs for details."
                ),
            }
            overall_status = "FAIL"
            results.append(result)
            continue

        if result["status"] == "FAIL":
            overall_status = "FAIL"
        results.append(result)
        logger.info(f"Check '{check_name}': {result['status']}")

    logger.info(f"Data quality checks complete: {overall_status}")

    return {
        "overall_status": overall_status,
        "run_timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "correlation_id": correlation_id,
        "total_rows": total_rows,
        "checks": results,
    }


# ---------------------------------------------------------------------------
# Individual check implementations
# ---------------------------------------------------------------------------

def _check_not_null(df, check_name, column, total_rows):
    """Check that a column has no null/NaN values."""
    violation_count = _get_null_count(df, column)
    passed = violation_count == 0
    return {
        "check": check_name,
        "type": "not_null",
        "column": column,
        "total_rows": total_rows,
        "violation_count": violation_count,
        "status": "PASS" if passed else "FAIL",
    }


def _check_unique(df, check_name, column, total_rows):
    """Check that a column has no duplicate values."""
    violation_count = _get_duplicate_count(df, column, total_rows=total_rows)
    passed = violation_count == 0
    return {
        "check": check_name,
        "type": "unique",
        "column": column,
        "total_rows": total_rows,
        "violation_count": violation_count,
        "status": "PASS" if passed else "FAIL",
    }


def _check_range(df, check_name, column, parameters, total_rows):
    """Check that column values fall within the specified range."""
    min_val = parameters.get("min")
    max_val = parameters.get("max")
    violation_count = _get_out_of_range_count(df, column, min_val, max_val)
    passed = violation_count == 0
    return {
        "check": check_name,
        "type": "range",
        "column": column,
        "total_rows": total_rows,
        "violation_count": violation_count,
        "min": min_val,
        "max": max_val,
        "status": "PASS" if passed else "FAIL",
    }


def _check_regex(df, check_name, column, parameters, total_rows):
    """Check that column values match a regex pattern."""
    pattern = parameters.get("pattern", ".*")
    violation_count = _get_regex_violation_count(df, column, pattern)
    passed = violation_count == 0
    return {
        "check": check_name,
        "type": "regex",
        "column": column,
        "total_rows": total_rows,
        "violation_count": violation_count,
        "pattern": pattern,
        "status": "PASS" if passed else "FAIL",
    }


def _check_custom(df, check_name, column, parameters, total_rows):
    """
    Run a custom data quality check using a callable.

    The callable receives the DataFrame and column name and must return
    an integer violation count.

    Args:
        df: Target DataFrame.
        check_name: Name of the check.
        column: Column to check (passed to the callable).
        parameters: Must contain 'callable' key with a callable accepting
                    (df, column) and returning int violation count.
        total_rows: Total row count.

    Returns:
        Result dict with check details and status.
    """
    check_fn = parameters.get("callable")
    if check_fn is None or not callable(check_fn):
        return {
            "check": check_name,
            "type": "custom",
            "column": column,
            "status": "ERROR",
            "message": "No callable provided in parameters['callable']",
        }

    violation_count = int(check_fn(df, column))
    passed = violation_count == 0
    return {
        "check": check_name,
        "type": "custom",
        "column": column,
        "total_rows": total_rows,
        "violation_count": violation_count,
        "status": "PASS" if passed else "FAIL",
    }
