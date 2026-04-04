"""
Reconciliation logic tests for monthly_revenue_by_category.

Tests each reconciliation rule type (row_count, sum, distinct_count,
null_check), tolerance handling, and error cases using the
templates/common/reconciliation.py module.
"""
import logging

import pytest
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
)

# Module under test
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from templates.common.reconciliation import (
    run_reconciliation,
    _calculate_diff_pct,
    _extract_column_from_expr,
    _get_row_count,
    _get_column_sum,
    _get_distinct_count,
    _get_null_count,
)


@pytest.fixture
def recon_logger():
    """Logger for reconciliation tests."""
    logger = logging.getLogger("test_recon")
    logger.setLevel(logging.DEBUG)
    return logging.LoggerAdapter(logger, {"correlation_id": "recon-test"})


# ===================================================================
# Row Count Rule Tests
# ===================================================================

class TestRowCountRule:
    """Tests for the row_count reconciliation rule type."""

    def test_row_count_exact_match(self, spark, recon_logger):
        """Row count rule should PASS when source and target counts match."""
        source = spark.createDataFrame([(1,), (2,), (3,)], ["id"])
        target = spark.createDataFrame([(1,), (2,), (3,)], ["id"])
        rules = [{"name": "row_count_test", "type": "row_count", "tolerance_pct": 0.0,
                  "source_expr": "SELECT COUNT(*)", "target_expr": "SELECT COUNT(*)"}]
        result = run_reconciliation(rules, recon_logger, source_df=source, target_df=target)
        assert result["overall_status"] == "PASS"
        assert result["rules"][0]["status"] == "PASS"

    def test_row_count_mismatch_fails(self, spark, recon_logger):
        """Row count rule should FAIL when counts differ beyond tolerance."""
        source = spark.createDataFrame([(1,), (2,), (3,), (4,)], ["id"])
        target = spark.createDataFrame([(1,), (2,)], ["id"])
        rules = [{"name": "row_count_test", "type": "row_count", "tolerance_pct": 0.0,
                  "source_expr": "SELECT COUNT(*)", "target_expr": "SELECT COUNT(*)"}]
        result = run_reconciliation(rules, recon_logger, source_df=source, target_df=target)
        assert result["overall_status"] == "FAIL"
        assert result["rules"][0]["status"] == "FAIL"

    def test_row_count_within_tolerance(self, spark, recon_logger):
        """Row count rule should PASS when difference is within tolerance."""
        source = spark.createDataFrame([(i,) for i in range(100)], ["id"])
        target = spark.createDataFrame([(i,) for i in range(99)], ["id"])
        rules = [{"name": "row_count_test", "type": "row_count", "tolerance_pct": 2.0,
                  "source_expr": "SELECT COUNT(*)", "target_expr": "SELECT COUNT(*)"}]
        result = run_reconciliation(rules, recon_logger, source_df=source, target_df=target)
        assert result["rules"][0]["status"] == "PASS"


# ===================================================================
# Sum Rule Tests
# ===================================================================

class TestSumRule:
    """Tests for the sum reconciliation rule type."""

    def test_sum_exact_match(self, spark, recon_logger):
        """Sum rule should PASS when source and target sums match."""
        source = spark.createDataFrame([(10.0,), (20.0,), (30.0,)], ["amount"])
        target = spark.createDataFrame([(60.0,)], ["total_revenue"])
        # Use executor mode for precise control
        rules = [{"name": "sum_test", "type": "sum", "tolerance_pct": 0.0,
                  "source_expr": "SELECT SUM(amount)", "target_expr": "SELECT SUM(total_revenue)"}]
        result = run_reconciliation(rules, recon_logger, source_df=source, target_df=target)
        assert result["rules"][0]["status"] == "PASS"

    def test_sum_mismatch_fails(self, spark, recon_logger):
        """Sum rule should FAIL when sums differ beyond tolerance."""
        source = spark.createDataFrame([(100.0,), (200.0,)], ["amount"])
        target = spark.createDataFrame([(50.0,)], ["total_revenue"])
        rules = [{"name": "sum_test", "type": "sum", "tolerance_pct": 0.0,
                  "source_expr": "SELECT SUM(amount)", "target_expr": "SELECT SUM(total_revenue)"}]
        result = run_reconciliation(rules, recon_logger, source_df=source, target_df=target)
        assert result["rules"][0]["status"] == "FAIL"

    def test_sum_within_tolerance(self, spark, recon_logger):
        """Sum rule should PASS when difference is within tolerance_pct."""
        source = spark.createDataFrame([(100.0,)], ["amount"])
        target = spark.createDataFrame([(99.5,)], ["total_revenue"])
        rules = [{"name": "sum_test", "type": "sum", "tolerance_pct": 1.0,
                  "source_expr": "SELECT SUM(amount)", "target_expr": "SELECT SUM(total_revenue)"}]
        result = run_reconciliation(rules, recon_logger, source_df=source, target_df=target)
        assert result["rules"][0]["status"] == "PASS"
        assert result["rules"][0]["diff_pct"] <= 1.0


# ===================================================================
# Distinct Count Rule Tests
# ===================================================================

class TestDistinctCountRule:
    """Tests for the distinct_count reconciliation rule type."""

    def test_distinct_count_match(self, spark, recon_logger):
        """Distinct count should PASS when counts match."""
        source = spark.createDataFrame(
            [(1, "A"), (2, "B"), (3, "A"), (4, "C")], ["id", "category"]
        )
        target = spark.createDataFrame(
            [("A",), ("B",), ("C",)], ["product_category"]
        )
        rules = [{"name": "distinct_test", "type": "distinct_count", "tolerance_pct": 0.0,
                  "source_expr": "SELECT COUNT(DISTINCT category)",
                  "target_expr": "SELECT COUNT(DISTINCT product_category)"}]
        result = run_reconciliation(rules, recon_logger, source_df=source, target_df=target)
        assert result["rules"][0]["status"] == "PASS"

    def test_distinct_count_mismatch(self, spark, recon_logger):
        """Distinct count should FAIL when counts differ."""
        source = spark.createDataFrame(
            [(1, "A"), (2, "B"), (3, "C"), (4, "D")], ["id", "category"]
        )
        target = spark.createDataFrame([("A",), ("B",)], ["product_category"])
        rules = [{"name": "distinct_test", "type": "distinct_count", "tolerance_pct": 0.0,
                  "source_expr": "SELECT COUNT(DISTINCT category)",
                  "target_expr": "SELECT COUNT(DISTINCT product_category)"}]
        result = run_reconciliation(rules, recon_logger, source_df=source, target_df=target)
        assert result["rules"][0]["status"] == "FAIL"


# ===================================================================
# Null Check Rule Tests
# ===================================================================

class TestNullCheckRule:
    """Tests for the null_check reconciliation rule type."""

    def test_null_check_passes_no_nulls(self, spark, recon_logger):
        """Null check should PASS when target column has no nulls."""
        target = spark.createDataFrame(
            [("Electronics",), ("Furniture",)], ["product_category"]
        )
        rules = [{
            "name": "no_null_categories", "type": "null_check",
            "source_expr": "N/A",
            "target_expr": "SELECT COUNT(product_category) WHERE product_category IS NULL",
        }]
        result = run_reconciliation(rules, recon_logger, target_df=target)
        assert result["rules"][0]["status"] == "PASS"
        assert result["rules"][0]["null_count"] == 0

    def test_null_check_fails_with_nulls(self, spark, recon_logger):
        """Null check should FAIL when target column has null values."""
        target = spark.createDataFrame(
            [("Electronics",), (None,), ("Furniture",)], ["product_category"]
        )
        rules = [{
            "name": "no_null_categories", "type": "null_check",
            "source_expr": "N/A",
            "target_expr": "SELECT COUNT(product_category) WHERE product_category IS NULL",
        }]
        result = run_reconciliation(rules, recon_logger, target_df=target)
        assert result["rules"][0]["status"] == "FAIL"
        assert result["rules"][0]["null_count"] == 1


# ===================================================================
# Tolerance Handling Tests
# ===================================================================

class TestToleranceHandling:
    """Tests for tolerance boundary conditions."""

    def test_exactly_at_tolerance_passes(self, spark, recon_logger):
        """Difference exactly at tolerance_pct should PASS."""
        source = spark.createDataFrame([(100.0,)], ["amount"])
        target = spark.createDataFrame([(99.0,)], ["total_revenue"])
        # diff = 1/100 * 100 = 1.0%
        rules = [{"name": "boundary", "type": "sum", "tolerance_pct": 1.0,
                  "source_expr": "SELECT SUM(amount)",
                  "target_expr": "SELECT SUM(total_revenue)"}]
        result = run_reconciliation(rules, recon_logger, source_df=source, target_df=target)
        assert result["rules"][0]["status"] == "PASS"

    def test_just_beyond_tolerance_fails(self, spark, recon_logger):
        """Difference slightly beyond tolerance_pct should FAIL."""
        source = spark.createDataFrame([(100.0,)], ["amount"])
        target = spark.createDataFrame([(98.0,)], ["total_revenue"])
        # diff = 2/100 * 100 = 2.0%
        rules = [{"name": "boundary", "type": "sum", "tolerance_pct": 1.0,
                  "source_expr": "SELECT SUM(amount)",
                  "target_expr": "SELECT SUM(total_revenue)"}]
        result = run_reconciliation(rules, recon_logger, source_df=source, target_df=target)
        assert result["rules"][0]["status"] == "FAIL"

    def test_zero_tolerance_requires_exact_match(self, spark, recon_logger):
        """Zero tolerance should require exact match."""
        source = spark.createDataFrame([(100.0,)], ["amount"])
        target = spark.createDataFrame([(100.001,)], ["total_revenue"])
        rules = [{"name": "exact", "type": "sum", "tolerance_pct": 0.0,
                  "source_expr": "SELECT SUM(amount)",
                  "target_expr": "SELECT SUM(total_revenue)"}]
        result = run_reconciliation(rules, recon_logger, source_df=source, target_df=target)
        assert result["rules"][0]["status"] == "FAIL"


# ===================================================================
# Error Cases
# ===================================================================

class TestErrorCases:
    """Tests for error handling in reconciliation."""

    def test_empty_dataframe_row_count(self, spark, recon_logger):
        """Empty DataFrames should produce row_count = 0."""
        source = spark.createDataFrame([], schema=StructType([StructField("id", LongType())]))
        target = spark.createDataFrame([], schema=StructType([StructField("id", LongType())]))
        rules = [{"name": "empty_test", "type": "row_count", "tolerance_pct": 0.0,
                  "source_expr": "SELECT COUNT(*)", "target_expr": "SELECT COUNT(*)"}]
        result = run_reconciliation(rules, recon_logger, source_df=source, target_df=target)
        assert result["rules"][0]["status"] == "PASS"
        assert result["rules"][0]["source_value"] == 0.0

    def test_unknown_rule_type_skipped(self, spark, recon_logger):
        """Unknown rule type should be skipped, not cause failure."""
        source = spark.createDataFrame([(1,)], ["id"])
        target = spark.createDataFrame([(1,)], ["id"])
        rules = [{"name": "unknown", "type": "nonexistent_type",
                  "source_expr": "N/A", "target_expr": "N/A"}]
        result = run_reconciliation(rules, recon_logger, source_df=source, target_df=target)
        assert result["rules"][0]["status"] == "SKIP"
        # Overall should still be PASS (skips don't count as failures)
        assert result["overall_status"] == "PASS"

    def test_multiple_rules_mixed_results(self, spark, recon_logger):
        """Multiple rules: one PASS, one FAIL should result in overall FAIL."""
        source = spark.createDataFrame([(1, 100.0), (2, 200.0)], ["id", "amount"])
        target = spark.createDataFrame([(1, 50.0)], ["id", "total_revenue"])
        rules = [
            {"name": "row_count", "type": "row_count", "tolerance_pct": 0.0,
             "source_expr": "SELECT COUNT(*)", "target_expr": "SELECT COUNT(*)"},
            {"name": "sum_check", "type": "sum", "tolerance_pct": 0.0,
             "source_expr": "SELECT SUM(amount)", "target_expr": "SELECT SUM(total_revenue)"},
        ]
        result = run_reconciliation(rules, recon_logger, source_df=source, target_df=target)
        assert result["overall_status"] == "FAIL"
        statuses = {r["rule"]: r["status"] for r in result["rules"]}
        assert statuses["row_count"] == "FAIL"
        assert statuses["sum_check"] == "FAIL"

    def test_result_includes_correlation_id(self, spark, recon_logger):
        """Result should include the provided correlation_id."""
        source = spark.createDataFrame([(1,)], ["id"])
        target = spark.createDataFrame([(1,)], ["id"])
        rules = [{"name": "test", "type": "row_count", "tolerance_pct": 0.0,
                  "source_expr": "SELECT COUNT(*)", "target_expr": "SELECT COUNT(*)"}]
        result = run_reconciliation(
            rules, recon_logger, correlation_id="test-corr-123",
            source_df=source, target_df=target,
        )
        assert result["correlation_id"] == "test-corr-123"


# ===================================================================
# Helper Function Unit Tests
# ===================================================================

class TestHelperFunctions:
    """Unit tests for reconciliation helper functions."""

    def test_calculate_diff_pct_sum(self):
        """diff_pct for sum uses abs(source) as denominator."""
        assert _calculate_diff_pct(100, 99, "sum") == pytest.approx(1.0)
        assert _calculate_diff_pct(-100, -99, "sum") == pytest.approx(1.0)

    def test_calculate_diff_pct_row_count(self):
        """diff_pct for row_count uses max(source, 1) as denominator."""
        assert _calculate_diff_pct(100, 99, "row_count") == pytest.approx(1.0)

    def test_calculate_diff_pct_zero_source(self):
        """When source is 0, denominator should be 1 to avoid division by zero."""
        result = _calculate_diff_pct(0, 5, "row_count")
        assert result == 500.0

    def test_extract_column_sum(self):
        assert _extract_column_from_expr("SELECT SUM(total_amount) FROM t") == "total_amount"

    def test_extract_column_count_distinct(self):
        assert _extract_column_from_expr("SELECT COUNT(DISTINCT category) FROM t") == "category"

    def test_extract_column_count(self):
        assert _extract_column_from_expr("SELECT COUNT(order_id) FROM t") == "order_id"

    def test_extract_column_no_match(self):
        assert _extract_column_from_expr("SELECT * FROM t") is None
