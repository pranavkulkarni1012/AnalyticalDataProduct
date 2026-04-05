"""
Config schema validation tests for the SQL-driven pipeline architecture.

Tests that pipeline config YAMLs conform to the updated schema where:
- 'source' (singular) replaces 'sources' (array) -- connection info only
- 'query' replaces 'transformations' -- contains the SQL with CTEs/joins/aggregations
- Pipeline code is generic and shared; the config is the product-specific artifact
"""
import json
import os

import pytest
import yaml
from jsonschema import Draft7Validator, ValidationError


@pytest.fixture
def schema():
    """Load the pipeline config JSON schema."""
    schema_path = os.path.join(
        os.path.dirname(__file__), "..", "schemas", "pipeline_config_schema.json"
    )
    with open(schema_path, "r") as f:
        return json.load(f)


@pytest.fixture
def sample_config():
    """Load the monthly_revenue_by_category sample config."""
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "configs", "monthly_revenue_by_category.yaml"
    )
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


@pytest.fixture
def validator(schema):
    """Create a Draft7Validator from the schema."""
    return Draft7Validator(schema)


# ===================================================================
# Schema Validation Tests
# ===================================================================

class TestSchemaValidation:
    """Tests that the sample config passes schema validation."""

    def test_sample_config_is_valid(self, validator, sample_config):
        """The sample config should pass schema validation with no errors."""
        errors = list(validator.iter_errors(sample_config))
        assert errors == [], f"Validation errors: {[e.message for e in errors]}"

    def test_required_top_level_keys(self, sample_config):
        """Config must have all 7 required top-level keys."""
        required = {"product", "compute", "source", "query", "target", "reconciliation", "runtime"}
        assert required <= set(sample_config.keys())

    def test_no_sources_key(self, sample_config):
        """Config should use 'source' (singular), not 'sources' (array)."""
        assert "sources" not in sample_config
        assert "source" in sample_config

    def test_no_transformations_key(self, sample_config):
        """Config should use 'query' with SQL, not 'transformations'."""
        assert "transformations" not in sample_config
        assert "query" in sample_config


# ===================================================================
# Source Section Tests
# ===================================================================

class TestSourceSection:
    """Tests for the source connection configuration."""

    def test_source_is_snowflake(self, sample_config):
        """Source type must be snowflake."""
        assert sample_config["source"]["type"] == "snowflake"

    def test_source_has_connection(self, sample_config):
        """Source must have connection details."""
        conn = sample_config["source"]["connection"]
        assert "account" in conn
        assert "warehouse" in conn
        assert "role" in conn
        assert "authenticator" in conn

    def test_authenticator_is_oauth(self, sample_config):
        """Authenticator must be oauth."""
        assert sample_config["source"]["connection"]["authenticator"] == "oauth"

    def test_source_has_no_table_definition(self, sample_config):
        """Source should NOT have database/schema/table/columns -- those are in the SQL."""
        source = sample_config["source"]
        assert "database" not in source
        assert "schema" not in source
        assert "table" not in source
        assert "columns" not in source


# ===================================================================
# Query Section Tests
# ===================================================================

class TestQuerySection:
    """Tests for the SQL query configuration."""

    def test_query_has_sql(self, sample_config):
        """Query section must have a sql field."""
        assert "sql" in sample_config["query"]
        assert len(sample_config["query"]["sql"].strip()) > 0

    def test_sql_is_select_only(self, sample_config):
        """SQL should start with SELECT or WITH (no DML)."""
        sql = sample_config["query"]["sql"].strip().upper()
        assert sql.startswith("WITH") or sql.startswith("SELECT")

    def test_sql_has_no_dml(self, sample_config):
        """SQL must not contain DML/DDL keywords."""
        sql = sample_config["query"]["sql"].upper()
        forbidden = ["INSERT INTO", "MERGE INTO", "UPDATE ", "DELETE FROM",
                      "CREATE TABLE", "DROP TABLE", "ALTER TABLE", "TRUNCATE"]
        for keyword in forbidden:
            assert keyword not in sql, f"SQL contains forbidden keyword: {keyword}"

    def test_sql_uses_ctes(self, sample_config):
        """Sample SQL should use CTEs (WITH clause)."""
        sql = sample_config["query"]["sql"].strip().upper()
        assert sql.startswith("WITH"), "SQL should use CTEs for transformations"

    def test_sql_uses_fully_qualified_names(self, sample_config):
        """SQL should use fully-qualified table names (DATABASE.SCHEMA.TABLE)."""
        sql = sample_config["query"]["sql"]
        # Check for at least one fully-qualified reference
        assert '"PROD_DB"' in sql or "PROD_DB" in sql


# ===================================================================
# Target Section Tests
# ===================================================================

class TestTargetSection:
    """Tests for the Iceberg target configuration."""

    def test_catalog_is_glue(self, sample_config):
        """Target catalog must be glue_catalog."""
        assert sample_config["target"]["catalog"] == "glue_catalog"

    def test_format_is_iceberg(self, sample_config):
        """Target format must be iceberg."""
        assert sample_config["target"]["format"] == "iceberg"

    def test_s3_path_format(self, sample_config):
        """S3 path must start with s3://."""
        assert sample_config["target"]["s3_path"].startswith("s3://")

    def test_write_mode_valid(self, sample_config):
        """Write mode must be overwrite or append."""
        assert sample_config["target"]["write_mode"] in ("overwrite", "append")


# ===================================================================
# Reconciliation Section Tests
# ===================================================================

class TestReconciliationSection:
    """Tests for reconciliation rules."""

    def test_has_at_least_one_rule(self, sample_config):
        """Reconciliation must have at least one rule."""
        assert len(sample_config["reconciliation"]["rules"]) >= 1

    def test_rules_have_required_fields(self, sample_config):
        """Each rule must have name, type, source_expr, target_expr, tolerance_pct."""
        for rule in sample_config["reconciliation"]["rules"]:
            assert "name" in rule
            assert "type" in rule
            assert "source_expr" in rule
            assert "target_expr" in rule
            assert "tolerance_pct" in rule

    def test_rule_types_valid(self, sample_config):
        """Rule types must be from the allowed set."""
        valid_types = {"row_count", "sum", "distinct_count", "null_check"}
        for rule in sample_config["reconciliation"]["rules"]:
            assert rule["type"] in valid_types


# ===================================================================
# Runtime Section Tests (Glue-specific for sample config)
# ===================================================================

class TestRuntimeSection:
    """Tests for engine-specific runtime configuration."""

    def test_glue_required_fields(self, sample_config):
        """Glue engine requires glue_version, worker_type, num_workers."""
        runtime = sample_config["runtime"]
        assert "glue_version" in runtime
        assert "worker_type" in runtime
        assert "num_workers" in runtime
        assert "timeout_minutes" in runtime

    def test_timeout_in_range(self, sample_config):
        """Timeout must be between 1 and 2880 minutes."""
        timeout = sample_config["runtime"]["timeout_minutes"]
        assert 1 <= timeout <= 2880


# ===================================================================
# Schema Rejection Tests
# ===================================================================

class TestSchemaRejections:
    """Tests that invalid configs are rejected by the schema."""

    def test_rejects_missing_query(self, validator, sample_config):
        """Config without query section should fail validation."""
        invalid = {k: v for k, v in sample_config.items() if k != "query"}
        errors = list(validator.iter_errors(invalid))
        assert len(errors) > 0

    def test_rejects_missing_source(self, validator, sample_config):
        """Config without source section should fail validation."""
        invalid = {k: v for k, v in sample_config.items() if k != "source"}
        errors = list(validator.iter_errors(invalid))
        assert len(errors) > 0

    def test_rejects_non_oauth_authenticator(self, validator, sample_config):
        """Config with non-oauth authenticator should fail validation."""
        invalid = dict(sample_config)
        invalid["source"] = dict(sample_config["source"])
        invalid["source"]["connection"] = dict(sample_config["source"]["connection"])
        invalid["source"]["connection"]["authenticator"] = "password"
        errors = list(validator.iter_errors(invalid))
        assert len(errors) > 0

    def test_rejects_empty_sql(self, validator, sample_config):
        """Config with empty SQL should fail validation."""
        invalid = dict(sample_config)
        invalid["query"] = {"sql": ""}
        errors = list(validator.iter_errors(invalid))
        assert len(errors) > 0
