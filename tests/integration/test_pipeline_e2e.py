"""
End-to-end integration test for the monthly_revenue_by_category pipeline.

Simulates the full pipeline flow using local Spark + mock data:
1. Read mock source data (no Snowflake needed)
2. Apply joins and transformations
3. Write to a local Iceberg table (using local warehouse)
4. Run reconciliation checks against the written data
5. Run data quality checks against the written data

Uses local filesystem instead of S3 for Iceberg table storage.
"""
import logging
import os
import sys

import pytest
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from templates.common.reconciliation import run_reconciliation
from templates.common.data_quality import run_data_quality_checks


@pytest.fixture
def e2e_logger():
    """Logger for integration tests."""
    logger = logging.getLogger("test_e2e")
    logger.setLevel(logging.DEBUG)
    return logging.LoggerAdapter(logger, {"correlation_id": "e2e-test"})


@pytest.fixture(scope="module")
def spark(tmp_path_factory):
    """
    Create a local SparkSession for integration tests.

    Uses getOrCreate so it safely reuses any existing session. Does NOT
    call stop() -- avoids killing a session shared with other test modules.
    """
    warehouse_dir = str(tmp_path_factory.mktemp("iceberg_warehouse"))
    session = (
        SparkSession.builder
        .master("local[*]")
        .appName("adp-integration-test")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.default.parallelism", "2")
        .config("spark.ui.enabled", "false")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.sql.warehouse.dir", warehouse_dir)
        .getOrCreate()
    )
    yield session


# ---------------------------------------------------------------------------
# Mock source data
# ---------------------------------------------------------------------------

ORDERS_DATA = [
    (1, 100, 10, "2025-01-15", 2, 29.99, 59.98, "COMPLETED"),
    (2, 101, 20, "2025-01-16", 1, 49.99, 49.99, "COMPLETED"),
    (3, 102, 10, "2025-01-17", 3, 29.99, 89.97, "COMPLETED"),
    (4, 100, 30, "2025-02-01", 1, 99.99, 99.99, "COMPLETED"),
    (5, 103, 20, "2025-02-10", 2, 49.99, 99.98, "COMPLETED"),
    (6, 104, 40, "2025-02-15", 1, 19.99, 19.99, "CANCELLED"),
    (7, 105, 10, "2025-03-01", 5, 29.99, 149.95, "COMPLETED"),
    (8, 106, 30, "2025-03-10", 1, 99.99, 99.99, "COMPLETED"),
]

ORDERS_SCHEMA = StructType([
    StructField("order_id", LongType(), False),
    StructField("customer_id", LongType(), False),
    StructField("product_id", LongType(), False),
    StructField("order_date", StringType(), False),
    StructField("quantity", IntegerType(), False),
    StructField("unit_price", DoubleType(), False),
    StructField("total_amount", DoubleType(), False),
    StructField("order_status", StringType(), False),
])

CATALOG_DATA = [
    (10, "Widget A", "Electronics", "Gadgets", "BrandX"),
    (20, "Widget B", "Electronics", "Accessories", "BrandY"),
    (30, "Premium Chair", "Furniture", "Seating", "BrandZ"),
    (40, "Basic Pen", "Office Supplies", "Writing", "BrandW"),
]

CATALOG_SCHEMA = StructType([
    StructField("product_id", LongType(), False),
    StructField("product_name", StringType(), False),
    StructField("category", StringType(), True),
    StructField("subcategory", StringType(), True),
    StructField("brand", StringType(), True),
])


class TestPipelineE2E:
    """Full end-to-end pipeline integration test."""

    def test_full_pipeline(self, spark, e2e_logger, tmp_path):
        """Execute the full ETL pipeline and validate output."""
        # ---- Step 1: Read mock sources ----
        orders_df = spark.createDataFrame(ORDERS_DATA, schema=ORDERS_SCHEMA)
        catalog_df = spark.createDataFrame(CATALOG_DATA, schema=CATALOG_SCHEMA)

        e2e_logger.info(f"Source orders: {orders_df.count()} rows")
        e2e_logger.info(f"Source catalog: {catalog_df.count()} rows")

        # ---- Step 2: Apply pre-join filters ----
        completed_orders = orders_df.filter("order_status = 'COMPLETED'")
        assert completed_orders.count() == 7  # 8 total - 1 CANCELLED

        # ---- Step 3: Join ----
        joined = completed_orders.join(catalog_df, on="product_id", how="inner")
        assert joined.count() == 7  # All completed orders have catalog entries

        # ---- Step 4: Transform (aggregate) ----
        target = (
            joined
            .withColumn(
                "revenue_month",
                F.date_trunc("month", F.to_date("order_date")),
            )
            .groupBy("category", "revenue_month")
            .agg(
                F.sum("total_amount").alias("total_revenue"),
                F.countDistinct("order_id").alias("order_count"),
                F.avg("total_amount").alias("avg_order_value"),
                F.sum("quantity").alias("total_units_sold"),
            )
            .withColumnRenamed("category", "product_category")
            .filter("total_revenue > 0")
        )

        e2e_logger.info(f"Target rows: {target.count()}")
        assert target.count() > 0

        # ---- Step 5: Write to local parquet (simulating Iceberg write) ----
        output_path = str(tmp_path / "monthly_revenue_by_category")
        target.write.mode("overwrite").parquet(output_path)

        # ---- Step 6: Read back and verify ----
        written = spark.read.parquet(output_path)
        assert written.count() == target.count()

        # ---- Step 7: Run reconciliation ----
        recon_rules = [
            {
                "name": "total_revenue_check",
                "type": "sum",
                "tolerance_pct": 0.01,
                "source_expr": "SELECT SUM(total_amount)",
                "target_expr": "SELECT SUM(total_revenue)",
            },
            {
                "name": "row_count_check",
                "type": "row_count",
                "tolerance_pct": 0.0,
                "source_expr": "SELECT COUNT(*)",
                "target_expr": "SELECT COUNT(*)",
            },
        ]

        # For recon, the "source" is the joined pre-aggregation data
        # and the "target" is the written output
        recon_result = run_reconciliation(
            recon_rules,
            e2e_logger,
            correlation_id="e2e-recon",
            source_df=joined,
            target_df=written,
        )

        # Revenue sum should match (source total_amount vs target total_revenue)
        revenue_rule = next(r for r in recon_result["rules"] if r["rule"] == "total_revenue_check")
        assert revenue_rule["status"] == "PASS"

        # ---- Step 8: Run data quality checks ----
        dq_checks = [
            {"name": "revenue_positive", "type": "range", "column": "total_revenue",
             "parameters": {"min": 0}},
            {"name": "category_not_null", "type": "not_null", "column": "product_category"},
            {"name": "order_count_positive", "type": "range", "column": "order_count",
             "parameters": {"min": 1}},
        ]

        dq_result = run_data_quality_checks(
            written, dq_checks, e2e_logger, correlation_id="e2e-dq"
        )
        assert dq_result["overall_status"] == "PASS"
        for check in dq_result["checks"]:
            assert check["status"] == "PASS", f"DQ check '{check['check']}' failed"

    def test_pipeline_data_integrity(self, spark, e2e_logger):
        """Verify data integrity: no revenue is lost or created in transformation."""


        orders_df = spark.createDataFrame(ORDERS_DATA, schema=ORDERS_SCHEMA)
        catalog_df = spark.createDataFrame(CATALOG_DATA, schema=CATALOG_SCHEMA)

        completed = orders_df.filter("order_status = 'COMPLETED'")
        joined = completed.join(catalog_df, on="product_id", how="inner")

        source_total = joined.agg(F.sum("total_amount")).collect()[0][0]
        source_units = joined.agg(F.sum("quantity")).collect()[0][0]

        target = (
            joined
            .withColumn("revenue_month", F.date_trunc("month", F.to_date("order_date")))
            .groupBy("category", "revenue_month")
            .agg(
                F.sum("total_amount").alias("total_revenue"),
                F.sum("quantity").alias("total_units_sold"),
            )
            .filter("total_revenue > 0")
        )

        target_total = target.agg(F.sum("total_revenue")).collect()[0][0]
        target_units = target.agg(F.sum("total_units_sold")).collect()[0][0]

        assert abs(source_total - target_total) < 0.01, "Revenue total mismatch"
        assert source_units == target_units, "Units sold mismatch"

    def test_pipeline_handles_empty_sources(self, spark, e2e_logger):
        """Pipeline should handle empty source data gracefully."""


        empty_orders = spark.createDataFrame([], schema=ORDERS_SCHEMA)
        catalog_df = spark.createDataFrame(CATALOG_DATA, schema=CATALOG_SCHEMA)

        completed = empty_orders.filter("order_status = 'COMPLETED'")
        joined = completed.join(catalog_df, on="product_id", how="inner")

        assert joined.count() == 0

        target = (
            joined
            .withColumn("revenue_month", F.date_trunc("month", F.to_date("order_date")))
            .groupBy("category", "revenue_month")
            .agg(F.sum("total_amount").alias("total_revenue"))
            .filter("total_revenue > 0")
        )

        assert target.count() == 0
