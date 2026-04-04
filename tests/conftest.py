"""
Shared test fixtures for all ADP test suites.

Provides common fixtures: temporary directories, logging setup,
mock AWS credentials, and config loading helpers.
"""
import json
import logging
import os
import tempfile

import pytest
import yaml


# ---------------------------------------------------------------------------
# AWS credential isolation -- ensures tests never hit real AWS
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_aws_env(monkeypatch):
    """Set dummy AWS credentials so boto3 never uses real credentials."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setenv("AWS_PROFILE", "nonexistent-adp-test")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

@pytest.fixture
def test_logger():
    """Return a logger suitable for passing to template functions."""
    logger = logging.getLogger("test")
    logger.setLevel(logging.DEBUG)
    adapter = logging.LoggerAdapter(logger, {"correlation_id": "test-0000"})
    return adapter


# ---------------------------------------------------------------------------
# Temporary directories
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_output_dir(tmp_path):
    """Return a temporary directory for test output files."""
    output = tmp_path / "output"
    output.mkdir()
    return output


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_config():
    """Load the monthly_revenue_by_category sample config."""
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "configs", "monthly_revenue_by_category.yaml"
    )
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


@pytest.fixture
def sample_schema():
    """Load the pipeline config JSON schema."""
    schema_path = os.path.join(
        os.path.dirname(__file__), "..", "schemas", "pipeline_config_schema.json"
    )
    with open(schema_path, "r") as f:
        return json.load(f)
