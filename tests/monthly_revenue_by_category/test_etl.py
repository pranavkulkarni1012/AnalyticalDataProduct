"""
ETL logic tests for monthly_revenue_by_category.

Tests join logic, aggregation logic, filter logic, and column mapping
using local Spark with mock DataFrames.
"""
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


# ===================================================================
# Join Logic Tests
# ===================================================================

class TestJoinLogic:
    """Tests for the inner join between customer_orders and product_catalog."""

    def test_join_produces_correct_columns(self, joined_df):
        """Joined DataFrame should contain columns from both sources."""
        columns = set(joined_df.columns)
        # From customer_orders
        assert "order_id" in columns
        assert "total_amount" in columns
        assert "order_date" in columns
        # From product_catalog
        assert "category" in columns
        assert "product_name" in columns
        # Join key present (deduplicated)
        assert "product_id" in columns

    def test_join_on_correct_key(self, joined_df, completed_orders_df, product_catalog_df):
        """Every product_id in the joined result must exist in both sources."""
        joined_ids = {
            row.product_id for row in joined_df.select("product_id").distinct().collect()
        }
        source_ids = {
            row.product_id
            for row in completed_orders_df.select("product_id").distinct().collect()
        }
        catalog_ids = {
            row.product_id
            for row in product_catalog_df.select("product_id").distinct().collect()
        }
        assert joined_ids <= source_ids
        assert joined_ids <= catalog_ids

    def test_inner_join_excludes_non_matching(
        self, spark, completed_orders_df, product_catalog_df
    ):
        """Inner join should drop orders whose product_id has no catalog entry."""
        # Add an order with a product_id that doesn't exist in catalog
        orphan = spark.createDataFrame(
            [(999, 200, 9999, "2025-04-01", 1, 10.0, 10.0, "COMPLETED")],
            schema=completed_orders_df.schema,
        )
        orders_with_orphan = completed_orders_df.union(orphan)
        joined = orders_with_orphan.join(
            product_catalog_df, on="product_id", how="inner"
        )
        joined_ids = {row.product_id for row in joined.select("product_id").distinct().collect()}
        assert 9999 not in joined_ids

    def test_join_row_count(self, joined_df, completed_orders_df):
        """Join count should match completed orders (all have catalog entries)."""
        assert joined_df.count() == completed_orders_df.count()


# ===================================================================
# Aggregation Logic Tests
# ===================================================================

class TestAggregationLogic:
    """Tests for sum, count_distinct, avg aggregations."""

    def test_total_revenue_sum(self, target_df, joined_df):
        """Sum of total_revenue in target should match sum of total_amount in source."""
        target_sum = target_df.agg(F.sum("total_revenue")).collect()[0][0]
        source_sum = joined_df.agg(F.sum("total_amount")).collect()[0][0]
        assert abs(target_sum - source_sum) < 0.01

    def test_order_count_distinct(self, target_df, joined_df):
        """Sum of order_count across all groups should equal distinct order count."""
        target_orders = target_df.agg(F.sum("order_count")).collect()[0][0]
        source_distinct = joined_df.select("order_id").distinct().count()
        assert target_orders == source_distinct

    def test_avg_order_value_positive(self, target_df):
        """Average order value should be positive for all groups."""
        min_avg = target_df.agg(F.min("avg_order_value")).collect()[0][0]
        assert min_avg > 0

    def test_total_units_sold(self, target_df, joined_df):
        """Sum of total_units_sold should match source quantity sum."""
        target_units = target_df.agg(F.sum("total_units_sold")).collect()[0][0]
        source_units = joined_df.agg(F.sum("quantity")).collect()[0][0]
        assert target_units == source_units

    def test_group_by_produces_unique_combinations(self, target_df):
        """Each (product_category, revenue_month) combination should be unique."""
        total = target_df.count()
        distinct = target_df.select("product_category", "revenue_month").distinct().count()
        assert total == distinct


# ===================================================================
# Filter Logic Tests
# ===================================================================

class TestFilterLogic:
    """Tests for pre-join and post-aggregation filters."""

    def test_completed_orders_only(self, completed_orders_df):
        """Only COMPLETED orders should survive the pre-join filter."""
        statuses = {
            row.order_status
            for row in completed_orders_df.select("order_status").distinct().collect()
        }
        assert statuses == {"COMPLETED"}

    def test_cancelled_orders_excluded(self, customer_orders_df, completed_orders_df):
        """CANCELLED orders should be filtered out."""
        assert completed_orders_df.count() < customer_orders_df.count()
        cancelled = completed_orders_df.filter("order_status = 'CANCELLED'").count()
        assert cancelled == 0

    def test_post_aggregation_filter_positive_revenue(self, target_df):
        """Post-aggregation filter: total_revenue > 0."""
        min_revenue = target_df.agg(F.min("total_revenue")).collect()[0][0]
        assert min_revenue > 0

    def test_null_dates_handled(self, spark):
        """Orders with null order_date should not cause failures in date aggregation."""
        orders = spark.createDataFrame(
            [(1, 100, 10, None, 1, 10.0, 10.0, "COMPLETED")],
            schema=StructType([
                StructField("order_id", LongType(), False),
                StructField("customer_id", LongType(), False),
                StructField("product_id", LongType(), False),
                StructField("order_date", StringType(), True),
                StructField("quantity", IntegerType(), False),
                StructField("unit_price", DoubleType(), False),
                StructField("total_amount", DoubleType(), False),
                StructField("order_status", StringType(), False),
            ]),
        )
        catalog = spark.createDataFrame(
            [(10, "Widget A", "Electronics", "Gadgets", "BrandX")],
            schema=StructType([
                StructField("product_id", LongType(), False),
                StructField("product_name", StringType(), False),
                StructField("category", StringType(), True),
                StructField("subcategory", StringType(), True),
                StructField("brand", StringType(), True),
            ]),
        )
        joined = orders.join(catalog, on="product_id", how="inner")
        result = (
            joined.withColumn(
                "revenue_month", F.date_trunc("month", F.to_date("order_date"))
            )
            .groupBy("category", "revenue_month")
            .agg(F.sum("total_amount").alias("total_revenue"))
        )
        # Should not raise; null dates become null revenue_month
        assert result.count() >= 0


# ===================================================================
# Column Mapping Tests
# ===================================================================

class TestColumnMapping:
    """Tests for column rename, cast, and derivation."""

    def test_category_renamed_to_product_category(self, target_df):
        """category should be renamed to product_category in the target."""
        assert "product_category" in target_df.columns
        assert "category" not in target_df.columns

    def test_revenue_month_derived(self, target_df):
        """revenue_month should be derived from date_trunc of order_date."""
        assert "revenue_month" in target_df.columns
        # All revenue_month values should be first-of-month
        months = [row.revenue_month for row in target_df.select("revenue_month").collect()]
        for m in months:
            if m is not None:
                assert m.day == 1

    def test_target_has_expected_columns(self, target_df):
        """Target should have exactly the expected output columns."""
        expected = {
            "product_category",
            "revenue_month",
            "total_revenue",
            "order_count",
            "avg_order_value",
            "total_units_sold",
        }
        assert set(target_df.columns) == expected

    def test_total_revenue_is_double(self, target_df):
        """total_revenue should be a numeric (double) type."""
        from pyspark.sql.types import DoubleType

        field = next(f for f in target_df.schema.fields if f.name == "total_revenue")
        assert isinstance(field.dataType, DoubleType)
