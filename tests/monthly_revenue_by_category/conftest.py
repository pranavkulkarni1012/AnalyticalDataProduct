"""
Product-specific fixtures for monthly_revenue_by_category tests.

Provides a session-scoped SparkSession in local mode, mock Snowflake
DataFrames with realistic sample data, and mock AWS Secrets Manager.
"""
import json

import boto3
import pytest
from moto import mock_aws
from pyspark.sql import SparkSession
from pyspark.sql.types import (
    DateType,
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
)


# ---------------------------------------------------------------------------
# SparkSession (session-scoped to avoid re-creation per test)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def spark():
    """Create a local SparkSession for testing."""
    session = (
        SparkSession.builder
        .master("local[*]")
        .appName("adp-unit-tests")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.default.parallelism", "2")
        .config("spark.ui.enabled", "false")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .getOrCreate()
    )
    yield session
    session.stop()


# ---------------------------------------------------------------------------
# Schemas matching the monthly_revenue_by_category config
# ---------------------------------------------------------------------------

CUSTOMER_ORDERS_SCHEMA = StructType([
    StructField("order_id", LongType(), False),
    StructField("customer_id", LongType(), False),
    StructField("product_id", LongType(), False),
    StructField("order_date", StringType(), False),
    StructField("quantity", IntegerType(), False),
    StructField("unit_price", DoubleType(), False),
    StructField("total_amount", DoubleType(), False),
    StructField("order_status", StringType(), False),
])

PRODUCT_CATALOG_SCHEMA = StructType([
    StructField("product_id", LongType(), False),
    StructField("product_name", StringType(), False),
    StructField("category", StringType(), True),
    StructField("subcategory", StringType(), True),
    StructField("brand", StringType(), True),
])


# ---------------------------------------------------------------------------
# Mock DataFrames with realistic sample data
# ---------------------------------------------------------------------------

@pytest.fixture
def customer_orders_df(spark):
    """Create a mock customer_orders DataFrame."""
    data = [
        (1, 100, 10, "2025-01-15", 2, 29.99, 59.98, "COMPLETED"),
        (2, 101, 20, "2025-01-16", 1, 49.99, 49.99, "COMPLETED"),
        (3, 102, 10, "2025-01-17", 3, 29.99, 89.97, "COMPLETED"),
        (4, 100, 30, "2025-02-01", 1, 99.99, 99.99, "COMPLETED"),
        (5, 103, 20, "2025-02-10", 2, 49.99, 99.98, "COMPLETED"),
        (6, 104, 40, "2025-02-15", 1, 19.99, 19.99, "CANCELLED"),
        (7, 105, 10, "2025-03-01", 5, 29.99, 149.95, "COMPLETED"),
        (8, 106, 30, "2025-03-10", 1, 99.99, 99.99, "COMPLETED"),
        (9, 107, 50, "2025-03-15", 2, 14.99, 29.98, "COMPLETED"),
        (10, 108, 20, "2025-03-20", 1, 49.99, 49.99, "COMPLETED"),
    ]
    return spark.createDataFrame(data, schema=CUSTOMER_ORDERS_SCHEMA)


@pytest.fixture
def product_catalog_df(spark):
    """Create a mock product_catalog DataFrame."""
    data = [
        (10, "Widget A", "Electronics", "Gadgets", "BrandX"),
        (20, "Widget B", "Electronics", "Accessories", "BrandY"),
        (30, "Premium Chair", "Furniture", "Seating", "BrandZ"),
        (40, "Basic Pen", "Office Supplies", "Writing", "BrandW"),
        (50, "Notebook", "Office Supplies", "Paper", "BrandV"),
    ]
    return spark.createDataFrame(data, schema=PRODUCT_CATALOG_SCHEMA)


@pytest.fixture
def completed_orders_df(spark, customer_orders_df):
    """Filter customer_orders to COMPLETED only (matches the config filter)."""
    return customer_orders_df.filter("order_status = 'COMPLETED'")


@pytest.fixture
def joined_df(completed_orders_df, product_catalog_df):
    """Join completed orders with product catalog on product_id."""
    return completed_orders_df.join(
        product_catalog_df, on="product_id", how="inner"
    )


# ---------------------------------------------------------------------------
# Aggregated target DataFrame (simulates the final Iceberg table contents)
# ---------------------------------------------------------------------------

@pytest.fixture
def target_df(spark, joined_df):
    """Aggregate joined data to produce the target monthly_revenue_by_category."""
    from pyspark.sql import functions as F

    result = (
        joined_df
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
    return result


# ---------------------------------------------------------------------------
# Mock AWS Secrets Manager
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_secrets_manager():
    """Mock AWS Secrets Manager with a test Snowflake OAuth secret."""
    with mock_aws():
        client = boto3.client("secretsmanager", region_name="us-east-1")
        client.create_secret(
            Name="adp/snowflake/company-prod.us-east-1/oauth",
            SecretString=json.dumps({
                "access_token": "mock-oauth-token-12345",
                "token_type": "Bearer",
                "expires_in": 3600,
            }),
        )
        yield client
