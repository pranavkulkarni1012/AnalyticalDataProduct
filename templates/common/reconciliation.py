"""
Reconciliation Template
Template: reconciliation.py

Provides the run_reconciliation() function that compares source data metrics
against target Iceberg table metrics. Works with both Spark DataFrames and
Pandas DataFrames using duck-typed adapters.

Supports rule types: row_count, sum, distinct_count, null_check.
Returns a structured result with overall_status (PASS/FAIL) and per-rule
results suitable for JSON serialization.

Used across all compute engines (Glue, EMR, Lambda, ECS).
"""
import logging
import uuid
import json
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
    """Get row count from either Spark or Pandas DataFrame."""
    if _is_spark_dataframe(df):
        return df.count()
    return len(df)


def _get_column_sum(df, column):
    """Get sum of a column from either Spark or Pandas DataFrame."""
    if _is_spark_dataframe(df):
        result = df.select(column).groupBy().sum().collect()[0][0]
        return float(result) if result is not None else 0.0
    return float(df[column].sum())


def _get_distinct_count(df, column):
    """Get distinct count of a column from either Spark or Pandas DataFrame."""
    if _is_spark_dataframe(df):
        return df.select(column).distinct().count()
    return df[column].nunique(dropna=False)


def _get_null_count(df, column):
    """Get null count of a column from either Spark or Pandas DataFrame."""
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


# ---------------------------------------------------------------------------
# Reconciliation engine
# ---------------------------------------------------------------------------

def _calculate_diff_pct(source_val, target_val, rule_type):
    """
    Calculate the percentage difference between source and target values.

    Uses max(abs(source_val), 1) for sum rules (handles negative sums)
    and max(source_val, 1) for count-based rules (always non-negative).

    Args:
        source_val: Source metric value.
        target_val: Target metric value.
        rule_type: Rule type string ('sum', 'row_count', 'distinct_count').

    Returns:
        Percentage difference as a float.
    """
    if rule_type == "sum":
        denominator = max(abs(source_val), 1)
    else:
        denominator = max(source_val, 1)
    return abs(source_val - target_val) / denominator * 100


def _extract_column_from_expr(expr):
    """
    Extract a column name from a SQL expression like
    'SELECT SUM(total_revenue) FROM ...'.

    Returns the column name or None if not parseable.
    """
    # Handle COUNT(DISTINCT col) separately from other aggregates
    match = re.search(
        r"COUNT\s*\(\s*DISTINCT\s+(\w+)\s*\)",
        expr,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)
    match = re.search(
        r"(?:SUM|COUNT|AVG|MIN|MAX)\s*\(\s*(\w+)\s*\)",
        expr,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)
    return None


def run_reconciliation(
    rules,
    logger,
    correlation_id=None,
    source_df=None,
    target_df=None,
    source_executor=None,
    target_executor=None,
):
    """
    Run reconciliation checks comparing source data against target data.

    Supports two modes of operation:
    1. DataFrame mode: Pass source_df and target_df directly (works with
       both Spark and Pandas DataFrames).
    2. Executor mode: Pass source_executor and target_executor callables
       that accept a SQL expression and return a scalar value. Used when
       source/target queries must be executed against external systems
       (e.g., Snowflake Spark connector for source, spark.sql for target).

    Args:
        rules: List of reconciliation rule dicts from the pipeline config.
            Each rule has: name, type, source_expr, target_expr, tolerance_pct.
        logger: Logger instance with correlation ID.
        correlation_id: Optional correlation ID for tracing.
        source_df: Source DataFrame (Spark or Pandas) for DataFrame mode.
        target_df: Target DataFrame (Spark or Pandas) for DataFrame mode.
        source_executor: Callable(sql_expr) -> scalar for executor mode.
        target_executor: Callable(sql_expr) -> scalar for executor mode.

    Returns:
        dict with:
            - overall_status: "PASS" or "FAIL"
            - run_timestamp: ISO-8601 timestamp
            - correlation_id: Correlation ID string
            - rules: List of per-rule result dicts
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    overall_status = "PASS"
    results = []

    logger.info(
        f"Starting reconciliation with {len(rules)} rules "
        f"(correlation_id={correlation_id})"
    )

    for rule in rules:
        rule_name = rule["name"]
        rule_type = rule["type"]
        tolerance_pct = rule.get("tolerance_pct", 0.0)

        try:
            if rule_type == "null_check":
                result = _process_null_check(
                    rule, logger,
                    target_df=target_df,
                    target_executor=target_executor,
                )
            elif rule_type in ("row_count", "sum", "distinct_count"):
                result = _process_comparison_rule(
                    rule, logger,
                    source_df=source_df,
                    target_df=target_df,
                    source_executor=source_executor,
                    target_executor=target_executor,
                )
            else:
                logger.warning(
                    f"Rule '{rule_name}': unknown type '{rule_type}', skipping"
                )
                result = {
                    "rule": rule_name,
                    "type": rule_type,
                    "status": "SKIP",
                    "message": f"Unknown rule type: {rule_type}",
                }
                results.append(result)
                continue

        except Exception:
            logger.error(
                f"Rule '{rule_name}' failed with error", exc_info=True
            )
            result = {
                "rule": rule_name,
                "type": rule_type,
                "status": "ERROR",
                "message": (
                    "Rule evaluation failed. "
                    "See pipeline logs for details."
                ),
            }
            overall_status = "FAIL"
            results.append(result)
            continue

        if result["status"] == "FAIL":
            overall_status = "FAIL"
        results.append(result)
        logger.info(f"Rule '{rule_name}': {result['status']}")

    logger.info(f"Reconciliation complete: {overall_status}")

    return {
        "overall_status": overall_status,
        "run_timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "correlation_id": correlation_id,
        "rules": results,
    }


def _process_null_check(rule, logger, target_df=None, target_executor=None):
    """
    Process a null_check rule. Only checks the target -- source_expr is N/A.

    Returns a result dict with rule, type, null_count, and status.
    """
    rule_name = rule["name"]
    target_expr = rule.get("target_expr", "")

    if target_executor is not None:
        null_count = target_executor(target_expr)
    elif target_df is not None:
        column = _extract_column_from_expr(target_expr)
        if column is None:
            raise ValueError(
                f"Rule '{rule_name}': cannot extract column from "
                f"target_expr '{target_expr}'"
            )
        null_count = _get_null_count(target_df, column)
    else:
        raise ValueError(
            f"Rule '{rule_name}': no target_df or target_executor provided"
        )

    passed = int(null_count) == 0
    return {
        "rule": rule_name,
        "type": "null_check",
        "null_count": int(null_count),
        "status": "PASS" if passed else "FAIL",
    }


def _process_comparison_rule(
    rule,
    logger,
    source_df=None,
    target_df=None,
    source_executor=None,
    target_executor=None,
):
    """
    Process a comparison rule (row_count, sum, distinct_count).

    Returns a result dict with rule, type, source_value, target_value,
    diff_pct, tolerance_pct, and status.
    """
    rule_name = rule["name"]
    rule_type = rule["type"]
    tolerance_pct = rule.get("tolerance_pct", 0.0)
    source_expr = rule.get("source_expr", "")
    target_expr = rule.get("target_expr", "")

    # Get source value
    if source_executor is not None:
        source_val = source_executor(source_expr)
    elif source_df is not None:
        source_val = _get_metric(source_df, rule_type, source_expr)
    else:
        raise ValueError(
            f"Rule '{rule_name}': no source_df or source_executor provided"
        )

    # Get target value
    if target_executor is not None:
        target_val = target_executor(target_expr)
    elif target_df is not None:
        target_val = _get_metric(target_df, rule_type, target_expr)
    else:
        raise ValueError(
            f"Rule '{rule_name}': no target_df or target_executor provided"
        )

    source_val = float(source_val) if source_val is not None else 0.0
    target_val = float(target_val) if target_val is not None else 0.0

    diff_pct = _calculate_diff_pct(source_val, target_val, rule_type)
    passed = diff_pct <= tolerance_pct

    return {
        "rule": rule_name,
        "type": rule_type,
        "source_value": source_val,
        "target_value": target_val,
        "diff_pct": round(diff_pct, 4),
        "tolerance_pct": tolerance_pct,
        "status": "PASS" if passed else "FAIL",
    }


def _get_metric(df, rule_type, expr):
    """
    Extract a metric from a DataFrame based on the rule type.

    Args:
        df: Spark or Pandas DataFrame.
        rule_type: One of 'row_count', 'sum', 'distinct_count'.
        expr: SQL expression (used to extract column name for sum/distinct).

    Returns:
        Scalar metric value.
    """
    if rule_type == "row_count":
        return _get_row_count(df)

    column = _extract_column_from_expr(expr)
    if column is None and hasattr(df, "columns"):
        columns = list(df.columns) if not _is_spark_dataframe(df) else [
            f.name for f in df.schema.fields
        ]
        column = columns[0] if columns else None

    if column is None:
        raise ValueError(
            f"Cannot extract column from expression: {expr}"
        )

    if rule_type == "sum":
        return _get_column_sum(df, column)
    elif rule_type == "distinct_count":
        return _get_distinct_count(df, column)

    raise ValueError(f"Unsupported rule type: {rule_type}")
