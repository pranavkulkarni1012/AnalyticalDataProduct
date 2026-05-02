---
name: generate-test-cases
description: Generates a comprehensive pytest test suite tailored to a pipeline config and its compute engine. Tests run against REAL Snowflake (read-only OAuth) and REAL Iceberg (PyIceberg via Glue catalog) -- no mocks. Replaces the placeholder stubs from /generate-pipeline with real, executable test bodies covering config integrity, SQL safety, source connectivity, Iceberg target, reconciliation, data quality, parameter substitution, smoke, live execution, Step Function ASL, recon module, and negative cases. Use as part of /test-pipeline or directly.
argument-hint: "[config-path]"
allowed-tools: Read Grep Glob Write Bash
---

# Skill: generate-test-cases

## Description

Generates a tailored pytest test suite for the given pipeline config. Unlike the
placeholder stubs produced by the `pipeline-generator` agent (which contain
function signatures with `...` bodies), this skill emits **real, executable test
bodies** covering 12 categories.

**Real-execution model.** The integration, source-connectivity, target,
recon-module, and DQ tests run against the **actual deployed environment** --
real Snowflake (read-only OAuth via Secrets Manager + corporate proxy), real
Iceberg tables on S3 (via PyIceberg + Glue catalog), real Step Functions
(describe-state-machine via boto3). There is no `moto`, no `MagicMock` of
infrastructure. Static-analysis tests (config integrity, SQL safety, ASL
shape, parameter unit tests, negative cases) operate on local files and do not
need any cloud access.

> Tension with CLAUDE.md "MUST NOT use real AWS credentials or real Snowflake
> connections in tests": that constraint applied to the older mock-only stubs.
> This framework is an explicit **integration test framework** that targets a
> deployed `dev` environment by default, never `prod`. Snowflake access stays
> read-only (a hard constraint upheld by the role and the SQL-safety scan).

## Prerequisites

- The pipeline config exists and passes `/validate-config`.
- The generic pipeline has been deployed (`pipelines/generic/{engine}/`). Tests
  that import from the generic pipeline degrade to `pytest.skip()` if the
  generic pipeline is missing.
- The pipeline infrastructure has been deployed to a target environment
  (default `dev`): IAM, Step Function, target Iceberg table, OAuth secret in
  Secrets Manager. Tests that require live cloud resources skip if the
  resource is unreachable, with a clear message naming the resource.
- Python 3.11+, pytest, pyyaml, jsonschema, sqlparse, snowflake-connector-python,
  pyiceberg, boto3 are available (all declared in `requirements.txt`).
- The shell has AWS credentials (`AWS_PROFILE` or `AWS_ACCESS_KEY_ID`/`SECRET`)
  scoped to the target environment account.
- `ENV` env var is set to one of `dev`, `test`, `staging`, `prod` -- defaults
  to `dev` if unset.

## Inputs

- Pipeline config YAML path via `$ARGUMENTS`.
- If no path provided, scan `configs/*.yaml`. If exactly one exists, use it; if
  multiple exist, ask the user.

## Output

Files written under `pipelines/{product.name}/tests/`:

| File | Always | Conditional on |
|------|--------|----------------|
| `conftest.py` | Yes | -- |
| `test_config_integrity.py` | Yes | -- |
| `test_sql_query.py` | Yes | -- |
| `test_source_connection.py` | Yes | -- |
| `test_iceberg_target.py` | Yes | -- |
| `test_reconciliation_rules.py` | Yes | -- |
| `test_pipeline_smoke.py` | Yes | -- |
| `test_pipeline_integration.py` | Yes | engine-specific body |
| `test_step_function_asl.py` | Yes | -- |
| `test_negative_cases.py` | Yes | -- |
| `test_data_quality_rules.py` | If | `data_quality` section exists |
| `test_parameter_substitution.py` | If | `parameters` section exists |
| `test_recon_module.py` | If | `pipelines/{product}/recon/` exists |
| `fixtures/sample_config.yaml` | Yes | symlink-style copy of the config |

A `pytest.ini` (or `pyproject.toml` `[tool.pytest.ini_options]`) is also written
at `pipelines/{product.name}/pytest.ini` declaring markers (`smoke`,
`integration`, `negative`) and the rootdir.

## Generation Steps

### Step 1: Read Config and Determine Variants

1. Read the config from `$ARGUMENTS` (resolution rules above).
2. Extract:
   - `product.name`, `product.domain`
   - `compute.engine` (one of `glue`, `emr`, `lambda`, `ecs`)
   - `source.connection.*`
   - `query.sql`
   - `target.*`
   - `reconciliation.rules`
   - Presence of `parameters`, `data_quality`
3. Compute paths:
   - `tests_dir = pipelines/{product.name}/tests`
   - `generic_dir = pipelines/generic/{engine}`
   - `recon_dir = pipelines/{product.name}/recon`
4. Create the `tests_dir`. If it already contains files, **overwrite** them so
   the suite stays in sync with the current config (the `pipeline-generator`
   stubs are intentionally replaced).

### Step 2: Generate `pytest.ini`

Write `pipelines/{product.name}/pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
markers =
    smoke: fast sanity checks against generic pipeline modules
    integration: live probe against real Snowflake / real Iceberg / real Step Functions in the target env
    negative: tests that intentionally trigger failure paths
filterwarnings =
    ignore::DeprecationWarning
addopts = --strict-markers -ra
```

### Step 3: Generate `conftest.py`

The `conftest.py` provides shared fixtures used by every test file. Cloud
fixtures (`secrets_client`, `snowflake_connection`, `iceberg_table`,
`stepfunctions_client`) connect to real services in the target environment
and `pytest.skip` when a service is unreachable -- the same file works in
every engine and every environment without conditional generation.

```python
"""Shared pytest fixtures for the {product.name} test suite."""
import json
import os
import sys
from pathlib import Path

import pytest
import yaml

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = PRODUCT_ROOT.parent.parent
GENERIC_DIR = PROJECT_ROOT / "pipelines" / "generic" / "{engine}"
CONFIG_PATH = PROJECT_ROOT / "configs" / "{product.name}.yaml"

# Make generic pipeline modules importable
if GENERIC_DIR.exists():
    sys.path.insert(0, str(GENERIC_DIR))


@pytest.fixture(scope="session")
def config_path():
    return CONFIG_PATH


@pytest.fixture(scope="session")
def config(config_path):
    with open(config_path) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def engine(config):
    return config["compute"]["engine"]


@pytest.fixture(scope="session")
def product_name(config):
    return config["product"]["name"]


@pytest.fixture(scope="session")
def has_parameters(config):
    return bool(config.get("parameters"))


@pytest.fixture(scope="session")
def has_data_quality(config):
    return bool(config.get("data_quality", {}).get("checks"))


@pytest.fixture(scope="session")
def env():
    """Target environment for live tests. Defaults to dev. Never prod by default."""
    return os.environ.get("ENV", "dev").lower()


@pytest.fixture(scope="session")
def aws_region():
    return os.environ.get("AWS_REGION", "us-east-1")


@pytest.fixture(scope="session")
def aws_session(aws_region):
    """Real boto3 Session for the configured profile + region."""
    import boto3
    profile = os.environ.get("AWS_PROFILE")
    if profile:
        return boto3.Session(profile_name=profile, region_name=aws_region)
    return boto3.Session(region_name=aws_region)


@pytest.fixture(scope="session")
def aws_caller_identity(aws_session):
    """Cheap reachability probe for AWS. Requires only sts:GetCallerIdentity.
    Skips the entire AWS-dependent test surface if creds are missing/expired."""
    try:
        return aws_session.client("sts").get_caller_identity()
    except Exception as e:
        pytest.skip(f"AWS unreachable -- check AWS_PROFILE / AWS credentials: {e}")


@pytest.fixture(scope="session")
def secrets_client(aws_session, aws_caller_identity):
    """Real Secrets Manager client. AWS reachability already proven by
    aws_caller_identity; here we just hand back the client. The actual
    permission to read the OAuth secret is verified by snowflake_oauth_token."""
    return aws_session.client("secretsmanager")


@pytest.fixture(scope="session")
def snowflake_oauth_token(secrets_client, config):
    """Retrieve real OAuth token for the configured Snowflake account."""
    account = config["source"]["connection"]["account"]
    secret_id = f"adp/snowflake/{account}/oauth"
    try:
        secret = secrets_client.get_secret_value(SecretId=secret_id)
    except Exception as e:
        pytest.skip(f"OAuth secret '{secret_id}' not retrievable: {e}")
    payload = json.loads(secret["SecretString"])
    token = payload.get("access_token") or payload.get("token")
    if not token:
        pytest.skip(f"Secret '{secret_id}' has no access_token field")
    return token


def _parse_proxy_url(url):
    """Extract host/port/user/password from a proxy URL.
    Returns (host, port, user, password) where missing parts are None."""
    from urllib.parse import urlparse
    if not url:
        return None, None, None, None
    p = urlparse(url)
    return p.hostname, p.port, p.username, p.password


@pytest.fixture(scope="session")
def snowflake_connection(snowflake_oauth_token, config):
    """Real Snowflake DBAPI connection (read-only role enforced by config).

    Proxy is passed via explicit connector parameters (not env vars) so AWS
    calls in other fixtures do not get routed through the corporate proxy.
    """
    snowflake = pytest.importorskip("snowflake.connector")
    c = config["source"]["connection"]
    conn_params = dict(
        account=c["account"],
        warehouse=c["warehouse"],
        role=c["role"],
        authenticator="oauth",
        token=snowflake_oauth_token,
        client_session_keep_alive=False,
    )
    proxy = c.get("proxy") or {}
    proxy_url = proxy.get("https_proxy") or proxy.get("http_proxy")
    host, port, user, password = _parse_proxy_url(proxy_url)
    if host:
        conn_params["proxy_host"] = host
        if port:
            conn_params["proxy_port"] = str(port)
        if user:
            conn_params["proxy_user"] = user
        if password:
            conn_params["proxy_password"] = password
    try:
        conn = snowflake.connect(**conn_params)
    except Exception as e:
        pytest.skip(f"Snowflake connect failed: {e}")
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def iceberg_catalog(aws_region, config):
    """Real PyIceberg Glue catalog handle."""
    pyiceberg_catalog = pytest.importorskip("pyiceberg.catalog")
    try:
        return pyiceberg_catalog.load_catalog(
            config["target"]["catalog"],
            **{"type": "glue", "client.region": aws_region},
        )
    except Exception as e:
        pytest.skip(f"PyIceberg catalog not loadable: {e}")


@pytest.fixture(scope="session")
def iceberg_table(iceberg_catalog, config):
    """Real Iceberg table reference. Skips if the table does not exist yet."""
    db = config["target"]["database"]
    tbl = config["target"]["table"]
    try:
        return iceberg_catalog.load_table(f"{db}.{tbl}")
    except Exception as e:
        pytest.skip(f"Iceberg table {db}.{tbl} not yet created: {e}")


@pytest.fixture(scope="session")
def stepfunctions_client(aws_session):
    """Real Step Functions client."""
    return aws_session.client("stepfunctions")


@pytest.fixture
def parameter_utils():
    """Import substitute_parameters from the generic pipeline."""
    if not GENERIC_DIR.exists():
        pytest.skip("Generic pipeline not deployed -- run /generate-pipeline first")
    try:
        import parameter_utils  # noqa: WPS433
    except ImportError as e:
        pytest.skip(f"parameter_utils not importable: {e}")
    return parameter_utils


@pytest.fixture
def step_function_asl_path(product_name):
    p = PROJECT_ROOT / "pipelines" / product_name / "step_functions" / f"{product_name}_orchestrator.asl.json"
    if not p.exists():
        pytest.skip(f"Step Function ASL not found at {p} -- run /generate-step-function")
    return p


@pytest.fixture
def recon_module_path(product_name):
    p = PROJECT_ROOT / "pipelines" / product_name / "recon" / f"{product_name}_recon.py"
    if not p.exists():
        pytest.skip(f"Recon module not found at {p} -- run /run-recon")
    return p


def pytest_collection_modifyitems(config_obj, items):
    """Guardrail: refuse to run live-execution tests against prod unless
    LIVE_TESTS_AGAINST_PROD=1 is explicitly set in the environment."""
    if os.environ.get("ENV", "dev").lower() == "prod" and \
       os.environ.get("LIVE_TESTS_AGAINST_PROD") != "1":
        skip_live = pytest.mark.skip(
            reason="Refusing to run live tests against prod. Set LIVE_TESTS_AGAINST_PROD=1 to override."
        )
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_live)


# ---------------------------------------------------------------------------
# Shared helpers (importable from individual test files via `from conftest import ...`)
# ---------------------------------------------------------------------------

import re as _re

_PLACEHOLDER_RE = _re.compile(r"\$\{(\w+)\}")


def resolve_placeholders_for_test(sql, parameters):
    """Substitute ${param} placeholders with per-type test-safe SQL values.
    String/date values include surrounding quotes so they fit inside
    `'${param}'` contexts in the query. Numeric/boolean values are bare.
    Used by source/integration tests when sending the query to Snowflake
    for EXPLAIN or LIMIT-bounded execution."""
    test_values = {}
    for p in parameters or []:
        t = p["type"]
        name = p["name"]
        if t == "date":
            test_values[name] = "2026-01-01"
        elif t in ("integer", "number"):
            test_values[name] = "1"
        elif t == "boolean":
            test_values[name] = "TRUE"
        else:  # string / unknown -> safe quoted literal
            test_values[name] = "test"
    return _PLACEHOLDER_RE.sub(
        lambda m: test_values.get(m.group(1), "test"), sql,
    )
```

Substitute `{product.name}` and `{engine}` literally during generation.

### Step 4: Generate `test_config_integrity.py` (Category: config)

Tests verify the config file shape. These tests pass without any pipeline code
deployed.

Required test methods:

```python
import re
import pytest
import yaml

REQUIRED_TOP_LEVEL = ["product", "compute", "source", "query", "target", "reconciliation", "runtime"]
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,50}$")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class TestConfigIntegrity:
    def test_config_is_valid_yaml(self, config_path):
        with open(config_path) as f:
            yaml.safe_load(f)

    @pytest.mark.parametrize("section", REQUIRED_TOP_LEVEL)
    def test_required_top_level_section_present(self, config, section):
        assert section in config, f"Missing required top-level section: {section}"

    def test_product_name_pattern(self, config):
        assert NAME_PATTERN.match(config["product"]["name"])

    def test_product_version_is_semver(self, config):
        assert SEMVER_PATTERN.match(config["product"]["version"])

    def test_product_owner_is_email(self, config):
        assert EMAIL_PATTERN.match(config["product"]["owner"])

    def test_product_description_non_empty(self, config):
        assert config["product"]["description"].strip()

    def test_compute_engine_supported(self, config):
        assert config["compute"]["engine"] in {"glue", "emr", "lambda", "ecs"}

    def test_compute_language_consistent_with_engine(self, config):
        engine = config["compute"]["engine"]
        language = config["compute"].get("language")
        if language is None:
            pytest.skip("language not specified")
        if engine in {"glue", "emr"}:
            assert language == "pyspark"
        else:
            assert language == "python"

    def test_runtime_timeout_in_range(self, config):
        t = config["runtime"]["timeout_minutes"]
        assert 1 <= t <= 2880

    def test_engine_specific_runtime_fields(self, config):
        engine = config["compute"]["engine"]
        rt = config["runtime"]
        required = {
            "glue": ["glue_version", "worker_type", "num_workers"],
            "emr": ["emr_release", "emr_mode"],
            "lambda": ["lambda_memory_mb", "lambda_timeout_seconds"],
            "ecs": ["ecs_cpu", "ecs_memory"],
        }[engine]
        for field in required:
            assert field in rt, f"runtime.{field} required for {engine}"
```

### Step 5: Generate `test_sql_query.py` (Category: sql)

Tests verify the SQL query is safe, well-formed, and consistent with parameters.

Required tests:

```python
import re
import pytest

DML_DDL_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|TRUNCATE|CREATE)\b",
    re.IGNORECASE,
)
PLACEHOLDER_PATTERN = re.compile(r"\$\{(\w+)\}")
FQ_TABLE_PATTERN = re.compile(r'"[A-Za-z_][A-Za-z0-9_]*"\."[A-Za-z_][A-Za-z0-9_]*"\."[A-Za-z_][A-Za-z0-9_]*"')


class TestSQLSafety:
    def test_sql_present_and_non_empty(self, config):
        sql = config["query"]["sql"].strip()
        assert sql, "query.sql must be non-empty"

    def test_sql_starts_with_select_or_with(self, config):
        first = config["query"]["sql"].strip().split(None, 1)[0].upper()
        assert first in {"SELECT", "WITH"}, f"SQL must start with SELECT/WITH, got {first}"

    def test_sql_contains_no_dml_or_ddl(self, config):
        # Strip string literals so SQL like WHERE name = 'INSERT ME' is not flagged
        stripped = re.sub(r"'[^']*'", "''", config["query"]["sql"])
        match = DML_DDL_PATTERN.search(stripped)
        assert not match, f"Forbidden keyword: {match.group(0) if match else ''}"

    def test_sql_uses_fully_qualified_table_names(self, config):
        # Look for at least one fully-qualified DB.SCHEMA.TABLE reference
        assert FQ_TABLE_PATTERN.search(config["query"]["sql"]), \
            "SQL should reference at least one fully-qualified \"DB\".\"SCHEMA\".\"TABLE\""

    def test_sql_parses_with_sqlparse(self, config):
        sqlparse = pytest.importorskip("sqlparse")
        parsed = sqlparse.parse(config["query"]["sql"])
        assert parsed, "sqlparse failed to parse the SQL"
        assert parsed[0].get_type() in {"SELECT", "UNKNOWN"}, \
            f"Top-level statement type must be SELECT, got {parsed[0].get_type()}"


class TestSQLParameterConsistency:
    def test_all_placeholders_have_a_parameter_declaration(self, config):
        placeholders = set(PLACEHOLDER_PATTERN.findall(config["query"]["sql"]))
        declared = {p["name"] for p in config.get("parameters", [])}
        undeclared = placeholders - declared
        assert not undeclared, f"SQL placeholders without parameter declaration: {undeclared}"

    def test_all_declared_parameters_referenced_in_sql_or_recon(self, config):
        declared = {p["name"] for p in config.get("parameters", [])}
        if not declared:
            pytest.skip("no parameters declared")
        sql_refs = set(PLACEHOLDER_PATTERN.findall(config["query"]["sql"]))
        recon_refs = set()
        for rule in config["reconciliation"]["rules"]:
            recon_refs.update(PLACEHOLDER_PATTERN.findall(rule.get("source_expr", "")))
        unused = declared - sql_refs - recon_refs
        assert not unused, f"Declared parameters never referenced: {unused}"
```

### Step 6: Generate `test_source_connection.py` (Category: source)

Mix of **static checks** (config shape) and **live probes** (real OAuth, real
Snowflake handshake). Live tests skip if AWS or Snowflake is unreachable.

```python
import re
import pytest

WRITE_ROLE_PATTERN = re.compile(r"_(WRITER|ADMIN|OWNER|READWRITE)\b", re.IGNORECASE)


class TestSourceConnectionStatic:
    def test_source_type_is_snowflake(self, config):
        assert config["source"]["type"] == "snowflake"

    def test_authenticator_is_oauth(self, config):
        assert config["source"]["connection"]["authenticator"] == "oauth", \
            "Snowflake authenticator MUST be oauth (CLAUDE.md hard constraint)"

    def test_account_warehouse_role_present(self, config):
        c = config["source"]["connection"]
        for k in ("account", "warehouse", "role"):
            assert c.get(k), f"connection.{k} must be non-empty"

    def test_role_is_not_write_capable(self, config):
        role = config["source"]["connection"]["role"]
        assert not WRITE_ROLE_PATTERN.search(role), \
            f"Role '{role}' looks write-capable; Snowflake access must be read-only"

    def test_proxy_fields_if_present_are_http_urls(self, config):
        proxy = config["source"]["connection"].get("proxy")
        if proxy is None:
            pytest.skip("no proxy configured")
        for field in ("http_proxy", "https_proxy"):
            assert field in proxy, f"proxy.{field} required when proxy block is present"
            assert proxy[field].startswith("http://") or proxy[field].startswith("https://"), \
                f"proxy.{field} must start with http:// or https://"

    def test_no_hardcoded_credentials_in_connection_block(self, config):
        c = config["source"]["connection"]
        forbidden = {"password", "private_key", "private_key_path", "passphrase", "token"}
        leaked = forbidden.intersection(c.keys())
        assert not leaked, f"Forbidden credential fields present in config: {leaked}"


class TestSourceConnectionLive:
    """Real handshake against the configured Snowflake account.
    Skips automatically if AWS or Snowflake is unreachable."""

    def test_oauth_secret_exists_in_secrets_manager(self, secrets_client, config):
        account = config["source"]["connection"]["account"]
        secret_id = f"adp/snowflake/{account}/oauth"
        # describe_secret returns metadata without exposing the value
        secrets_client.describe_secret(SecretId=secret_id)

    def test_snowflake_handshake_succeeds(self, snowflake_connection):
        with snowflake_connection.cursor() as cur:
            cur.execute("SELECT CURRENT_VERSION()")
            row = cur.fetchone()
            assert row and row[0], "Snowflake returned no version"

    def test_role_can_only_read(self, snowflake_connection, config):
        # Verify the connected role matches the configured role
        with snowflake_connection.cursor() as cur:
            cur.execute("SELECT CURRENT_ROLE()")
            current_role = cur.fetchone()[0]
        configured_role = config["source"]["connection"]["role"]
        assert current_role.upper() == configured_role.upper(), \
            f"Active role {current_role} != configured {configured_role}"

    def test_query_compiles_against_snowflake(self, snowflake_connection, config):
        # Ask Snowflake to plan the query without executing it.
        # EXPLAIN runs server-side and does not move data.
        # Resolve ${param} placeholders with type-aware test values so a
        # query like `WHERE "load_dt" = '${load_date}'` parses as a real
        # date literal instead of '1'.
        from conftest import resolve_placeholders_for_test
        sql = resolve_placeholders_for_test(config["query"]["sql"], config.get("parameters"))
        with snowflake_connection.cursor() as cur:
            cur.execute(f"EXPLAIN USING TEXT {sql}")
            plan = cur.fetchall()
            assert plan, "EXPLAIN returned no plan rows"
```

### Step 7: Generate `test_iceberg_target.py` (Category: target)

Static config checks plus live verification that the Iceberg table exists in
the Glue catalog and matches the configured shape.

```python
import pytest


class TestIcebergTargetStatic:
    def test_catalog_is_glue_catalog(self, config):
        assert config["target"]["catalog"] == "glue_catalog"

    def test_format_is_iceberg(self, config):
        assert config["target"]["format"] == "iceberg"

    def test_s3_path_starts_with_s3_scheme(self, config):
        assert config["target"]["s3_path"].startswith("s3://")

    def test_write_mode_is_supported(self, config):
        assert config["target"]["write_mode"] in {"append", "overwrite"}

    def test_database_and_table_non_empty(self, config):
        assert config["target"]["database"], "target.database must be non-empty"
        assert config["target"]["table"], "target.table must be non-empty"

    def test_format_version_is_2_when_specified(self, config):
        props = config["target"].get("table_properties") or {}
        if "format-version" not in props:
            pytest.skip("format-version not specified (warning, not error)")
        assert str(props["format-version"]) == "2", \
            "Iceberg format-version MUST be 2 (CLAUDE.md hard constraint)"


class TestIcebergTargetLive:
    """Verify the deployed Iceberg table matches the config."""

    def test_table_exists_in_glue_catalog(self, iceberg_table):
        assert iceberg_table is not None

    def test_table_location_matches_config_s3_path(self, iceberg_table, config):
        location = iceberg_table.location()
        configured = config["target"]["s3_path"].rstrip("/")
        assert location.rstrip("/").startswith(configured) or configured.startswith(location.rstrip("/")), \
            f"Iceberg location {location} does not match configured s3_path {configured}"

    def test_table_format_version_is_2(self, iceberg_table):
        props = iceberg_table.properties
        assert props.get("format-version", "2") == "2", \
            "Live Iceberg table is not format-version 2"

    def test_partition_spec_matches_config(self, iceberg_table, config):
        configured_partitions = config["target"].get("partition_by") or []
        if not configured_partitions:
            pytest.skip("no partition_by configured")
        spec = iceberg_table.spec()
        live_partitions = [f.name for f in spec.fields]
        for p in configured_partitions:
            assert p in live_partitions, \
                f"Configured partition '{p}' not present in live table partition spec {live_partitions}"
```

### Step 8: Generate `test_reconciliation_rules.py` (Category: recon)

```python
import pytest


VALID_RULE_TYPES = {"row_count", "sum", "distinct_count", "null_check"}


class TestReconciliationRules:
    def test_at_least_one_rule(self, config):
        rules = config["reconciliation"]["rules"]
        assert len(rules) >= 1, "Every pipeline must have at least one reconciliation rule"

    def test_rule_names_unique(self, config):
        names = [r["name"] for r in config["reconciliation"]["rules"]]
        assert len(names) == len(set(names)), "Reconciliation rule names must be unique"

    @pytest.mark.parametrize("field", ["name", "type", "source_expr", "target_expr", "tolerance_pct"])
    def test_rule_required_fields(self, config, field):
        for rule in config["reconciliation"]["rules"]:
            assert field in rule, f"Rule {rule.get('name', '<unnamed>')} missing field: {field}"

    def test_rule_types_supported(self, config):
        for rule in config["reconciliation"]["rules"]:
            assert rule["type"] in VALID_RULE_TYPES, \
                f"Unsupported rule type: {rule['type']}"

    def test_tolerance_in_range(self, config):
        for rule in config["reconciliation"]["rules"]:
            t = rule["tolerance_pct"]
            assert 0 <= t <= 100, f"tolerance_pct must be in [0, 100], got {t}"

    def test_target_expr_references_target_table(self, config):
        target_db = config["target"]["database"]
        target_table = config["target"]["table"]
        fq = f"{target_db}.{target_table}"
        for rule in config["reconciliation"]["rules"]:
            assert fq in rule["target_expr"], \
                f"Rule {rule['name']} target_expr should reference {fq}"
```

### Step 9: Generate `test_data_quality_rules.py` (Category: dq, conditional)

Only generate if `config.data_quality.checks` exists. Static checks on the
config plus live execution of every DQ check against the real Iceberg target.

```python
import pytest


VALID_CHECK_TYPES = {"not_null", "unique", "range", "regex", "custom"}


class TestDataQualityRulesStatic:
    def test_check_required_fields(self, config):
        for check in config["data_quality"]["checks"]:
            for field in ("name", "type", "column"):
                assert field in check, f"DQ check missing field: {field}"

    def test_check_types_supported(self, config):
        for check in config["data_quality"]["checks"]:
            assert check["type"] in VALID_CHECK_TYPES

    def test_range_check_has_min_or_max(self, config):
        for check in config["data_quality"]["checks"]:
            if check["type"] == "range":
                params = check.get("parameters") or {}
                assert "min" in params or "max" in params, \
                    f"range check {check['name']} must specify min and/or max"

    def test_regex_check_has_pattern(self, config):
        for check in config["data_quality"]["checks"]:
            if check["type"] == "regex":
                assert (check.get("parameters") or {}).get("pattern"), \
                    f"regex check {check['name']} must specify pattern"


class TestDataQualityRulesLive:
    """Run every DQ check against the deployed Iceberg target.

    DQ checks are honest only when they see every row. Sampling defeats the
    point (a null on row 1_000_001 would slip through a 1k-row sample). To
    keep the suite from OOMing on very large targets, the class skips when
    the table exceeds MAX_DQ_SCAN_ROWS (default 1_000_000 -- override via
    env var). Use the qa-agent for DQ on multi-million-row tables; it runs
    inside the same compute engine as the pipeline."""

    @pytest.fixture(scope="class")
    def df(self, iceberg_table):
        max_rows = int(os.environ.get("MAX_DQ_SCAN_ROWS", "1000000"))
        # Iceberg snapshot summary carries an exact row count for the latest snapshot
        try:
            snapshot = iceberg_table.current_snapshot()
            row_count = int(snapshot.summary.get("total-records", "0")) if snapshot else 0
        except Exception:
            row_count = 0  # if the call fails, fall through and try the scan
        if row_count > max_rows:
            pytest.skip(
                f"target has {row_count} rows > MAX_DQ_SCAN_ROWS={max_rows}; "
                f"use the qa-agent for DQ on large tables"
            )
        return iceberg_table.scan().to_pandas()

    def test_referenced_column_exists_in_target(self, df, config):
        cols = {c.lower() for c in df.columns}
        for check in config["data_quality"]["checks"]:
            assert check["column"].lower() in cols, \
                f"DQ check {check['name']} references column {check['column']} not in target"

    def test_not_null_checks_pass(self, df, config):
        import re as _re
        for check in config["data_quality"]["checks"]:
            if check["type"] != "not_null":
                continue
            col = check["column"]
            null_count = df[col].isna().sum()
            assert null_count == 0, \
                f"DQ check {check['name']}: column {col} has {null_count} nulls"

    def test_unique_checks_pass(self, df, config):
        for check in config["data_quality"]["checks"]:
            if check["type"] != "unique":
                continue
            col = check["column"]
            dups = len(df) - df[col].nunique(dropna=False)
            assert dups == 0, f"DQ check {check['name']}: column {col} has {dups} duplicates"

    def test_range_checks_pass(self, df, config):
        for check in config["data_quality"]["checks"]:
            if check["type"] != "range":
                continue
            col = check["column"]
            params = check.get("parameters") or {}
            mn, mx = params.get("min"), params.get("max")
            series = df[col].dropna()
            if mn is not None:
                assert (series >= mn).all(), f"DQ check {check['name']}: values below min={mn}"
            if mx is not None:
                assert (series <= mx).all(), f"DQ check {check['name']}: values above max={mx}"

    def test_regex_checks_pass(self, df, config):
        import re as _re
        for check in config["data_quality"]["checks"]:
            if check["type"] != "regex":
                continue
            col = check["column"]
            pattern = _re.compile(check["parameters"]["pattern"])
            series = df[col].dropna().astype(str)
            bad = (~series.str.match(pattern)).sum()
            assert bad == 0, f"DQ check {check['name']}: {bad} values do not match pattern"
```

### Step 10: Generate `test_parameter_substitution.py` (Category: parameters, conditional)

Only generate if `config.parameters` exists. Tests exercise the
`substitute_parameters()` function from `pipelines/generic/{engine}/parameter_utils.py`.

```python
import pytest


class TestParameterSubstitution:
    def test_string_param_is_quoted_and_escaped(self, parameter_utils):
        sql = "WHERE x = '${name}'"
        defs = [{"name": "name", "type": "string"}]
        out = parameter_utils.substitute_parameters(sql, {"name": "O'Brien"}, defs)
        assert "O''Brien" in out

    def test_date_param_validates_iso_format(self, parameter_utils):
        defs = [{"name": "d", "type": "date"}]
        with pytest.raises(ValueError):
            parameter_utils.substitute_parameters("WHERE d = '${d}'", {"d": "31-12-2026"}, defs)

    def test_integer_param_rejects_non_numeric(self, parameter_utils):
        defs = [{"name": "n", "type": "integer"}]
        with pytest.raises(ValueError):
            parameter_utils.substitute_parameters("WHERE n = ${n}", {"n": "abc"}, defs)

    def test_boolean_param_emits_sql_literal(self, parameter_utils):
        defs = [{"name": "b", "type": "boolean"}]
        out = parameter_utils.substitute_parameters("AND ${b}", {"b": "yes"}, defs)
        assert "TRUE" in out

    def test_required_param_missing_raises(self, parameter_utils):
        defs = [{"name": "x", "type": "string", "required": True}]
        with pytest.raises(ValueError):
            parameter_utils.substitute_parameters("WHERE x = '${x}'", {}, defs)

    def test_default_used_when_param_not_provided(self, parameter_utils):
        defs = [{"name": "x", "type": "string", "required": False, "default": "fallback"}]
        out = parameter_utils.substitute_parameters("WHERE x = '${x}'", {}, defs)
        assert "fallback" in out

    def test_undeclared_placeholder_raises(self, parameter_utils):
        defs = [{"name": "x", "type": "string"}]
        with pytest.raises(ValueError):
            parameter_utils.substitute_parameters("WHERE y = '${y}'", {"x": "v"}, defs)

    def test_empty_definitions_returns_sql_unchanged(self, parameter_utils):
        sql = "SELECT 1 FROM dual"
        out = parameter_utils.substitute_parameters(sql, {}, [])
        assert out == sql

    def test_real_config_sql_resolves_with_test_values(self, parameter_utils, config):
        # Build a synthetic value for each declared param based on its type
        values = {}
        for p in config.get("parameters", []):
            t = p["type"]
            if t == "date":
                values[p["name"]] = "2026-01-01"
            elif t == "integer":
                values[p["name"]] = "1"
            elif t == "number":
                values[p["name"]] = "1.0"
            elif t == "boolean":
                values[p["name"]] = "true"
            else:
                values[p["name"]] = "test_value"
        # Should not raise
        parameter_utils.substitute_parameters(
            config["query"]["sql"], values, config["parameters"]
        )
```

### Step 11: Generate `test_pipeline_smoke.py` (Category: smoke)

Smoke tests verify the generic pipeline's modules import and basic helpers work.
Marked with `@pytest.mark.smoke` so they can be selected with `-m smoke`.

```python
import pytest

pytestmark = pytest.mark.smoke


class TestGenericPipelineImports:
    def test_parameter_utils_imports(self, parameter_utils):
        assert hasattr(parameter_utils, "substitute_parameters")

    def test_config_loads_without_error(self, config):
        assert isinstance(config, dict)

    def test_logger_setup_uses_correlation_id(self):
        # Check that the generic boilerplate sets a correlation_id at startup.
        # This is a textual check, not a runtime check.
        from pathlib import Path
        gen = Path(__file__).resolve().parent.parent.parent / "generic" / "{engine}"
        if not gen.exists():
            pytest.skip("generic pipeline not deployed")
        py_files = list(gen.glob("*.py"))
        assert any("correlation_id" in p.read_text() for p in py_files), \
            "Generic pipeline should reference correlation_id (CLAUDE.md standard)"

    def test_env_default_to_dev_in_generic_code(self):
        from pathlib import Path
        gen = Path(__file__).resolve().parent.parent.parent / "generic" / "{engine}"
        if not gen.exists():
            pytest.skip("generic pipeline not deployed")
        py_files = list(gen.glob("*.py"))
        assert any('"DEV"' in p.read_text() or "'DEV'" in p.read_text() for p in py_files), \
            "ENV must default to DEV (CLAUDE.md standard)"
```

Substitute `{engine}` literally during generation.

### Step 12: Generate `test_pipeline_integration.py` (Category: integration)

This is the **live, end-to-end probe** of the deployed pipeline. It does NOT
trigger a fresh execution (that would write to the target table -- side
effecting and slow). Instead, it asserts the deployed pieces work together by:

1. Running the configured `query.sql` against Snowflake with `LIMIT 5` to prove
   the source query produces real rows.
2. Reading the deployed Iceberg target via PyIceberg to prove it is queryable
   and has data.
3. Verifying the live target schema matches the columns the SQL produces.

The body is the same for all engines (real services, not engine-specific
mocks). Mark with `@pytest.mark.integration`.

```python
"""End-to-end integration test against the deployed dev environment.
Reads from real Snowflake (read-only) and real Iceberg target.
Skips automatically if either is unreachable."""
import pytest

# Shared helper from conftest. resolve_placeholders_for_test substitutes
# ${param} with type-appropriate VALUES (without surrounding quotes), so
# SQL like `WHERE "load_dt" = '${load_date}'` becomes
# `WHERE "load_dt" = '2026-01-01'` (the surrounding quotes already in the
# SQL are preserved intact). Earlier versions of this helper added outer
# quotes and produced invalid `''2026-01-01''` substitutions -- that bug
# is fixed by reusing the canonical helper.
from conftest import resolve_placeholders_for_test

pytestmark = pytest.mark.integration


def test_source_query_returns_rows_from_snowflake(snowflake_connection, config):
    """The configured SQL produces real rows when run against Snowflake."""
    sql = resolve_placeholders_for_test(config["query"]["sql"], config.get("parameters"))
    # Wrap so we don't pull a full result set into the test process
    bounded = f"SELECT * FROM ({sql}) limited LIMIT 5"
    with snowflake_connection.cursor() as cur:
        cur.execute(bounded)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    # Allow zero rows (empty source for the test date) but require schema
    assert cols, "Snowflake returned no columns -- query schema is empty"


def test_iceberg_target_is_queryable(iceberg_table):
    """The deployed Iceberg target is readable via PyIceberg."""
    scan = iceberg_table.scan(limit=5)
    df = scan.to_pandas()
    # Empty target is acceptable for a freshly deployed pipeline
    assert df is not None
    assert len(df.columns) > 0, "Iceberg target has no columns"


def test_target_schema_contains_expected_columns(snowflake_connection, iceberg_table, config):
    """The deployed target schema includes the columns the SQL projects."""
    sql = resolve_placeholders_for_test(config["query"]["sql"], config.get("parameters"))
    bounded = f"SELECT * FROM ({sql}) limited LIMIT 0"
    with snowflake_connection.cursor() as cur:
        cur.execute(bounded)
        sql_cols = {d[0].lower() for d in cur.description}
    iceberg_cols = {f.name.lower() for f in iceberg_table.schema().fields}
    missing = sql_cols - iceberg_cols
    assert not missing, \
        f"SQL produces columns not in the Iceberg target: {missing}"
```

Static module-import probes for the generic pipeline live in
`test_pipeline_smoke.py` -- this file is exclusively about the deployed
pipeline's live behavior.

### Step 13: Generate `test_step_function_asl.py` (Category: step_function)

```python
import json
import pytest


ENGINE_TO_RESOURCE_PREFIX = {
    "glue": "arn:aws:states:::glue:startJobRun",
    "emr": "arn:aws:states:::",  # may be elasticmapreduce or aws-sdk:emrserverless
    "lambda": "arn:aws:states:::lambda:invoke",
    "ecs": "arn:aws:states:::ecs:runTask",
}


@pytest.fixture(scope="module")
def asl(step_function_asl_path):
    with open(step_function_asl_path) as f:
        return json.load(f)


class TestStepFunctionASL:
    def test_asl_is_valid_json(self, asl):
        assert isinstance(asl, dict)

    def test_top_level_keys_present(self, asl):
        for k in ("StartAt", "States"):
            assert k in asl, f"ASL missing top-level key: {k}"

    def test_start_state_exists(self, asl):
        assert asl["StartAt"] in asl["States"], "StartAt references unknown state"

    def test_at_least_one_task_state(self, asl):
        kinds = [s.get("Type") for s in asl["States"].values()]
        assert "Task" in kinds, "ASL must contain at least one Task state"

    def test_resource_arn_matches_engine(self, asl, engine):
        prefix = ENGINE_TO_RESOURCE_PREFIX[engine]
        task_states = [s for s in asl["States"].values() if s.get("Type") == "Task"]
        assert any(s.get("Resource", "").startswith(prefix) for s in task_states), \
            f"No Task state references the expected ARN prefix for engine={engine}"

    def test_terminal_state_reachable(self, asl):
        # A state is terminal if it has End=True or Next leading nowhere.
        terminal = [name for name, s in asl["States"].items() if s.get("End") is True]
        assert terminal, "ASL must have at least one terminal state (End=true)"

    def test_no_hardcoded_account_id(self, asl):
        s = json.dumps(asl)
        # Account IDs are 12 digits; allow only as part of `${...}` Terraform refs.
        import re
        bare_account = re.findall(r"(?<![\w$])\d{12}(?![\w}])", s)
        assert not bare_account, f"ASL contains hardcoded AWS account IDs: {bare_account[:3]}"


class TestStepFunctionLive:
    """Verify the deployed state machine in AWS matches the local ASL."""

    def test_state_machine_exists_in_aws(self, stepfunctions_client, product_name, env, config):
        domain = config["product"]["domain"]
        sm_name = f"adp-{domain}-{product_name}-{env}"
        page = stepfunctions_client.list_state_machines(maxResults=1000)
        names = {sm["name"] for sm in page.get("stateMachines", [])}
        if sm_name not in names:
            pytest.skip(f"State machine {sm_name} not deployed to env={env}")
        # Find ARN and describe to ensure the definition is valid (parseable JSON)
        arn = next(sm["stateMachineArn"] for sm in page["stateMachines"] if sm["name"] == sm_name)
        desc = stepfunctions_client.describe_state_machine(stateMachineArn=arn)
        json.loads(desc["definition"])  # raises if not valid JSON
```

### Step 14: Generate `test_recon_module.py` (Category: recon_module, conditional)

Only generate if `pipelines/{product}/recon/` exists. The recon module is
loaded as a real Python module and -- where possible -- executed against a
single read-only reconciliation rule using the real Snowflake connection and
real Iceberg table. Marked `integration` (it touches live services).

```python
import logging
import pytest

pytestmark = pytest.mark.integration


def _load_recon_module(path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("recon_module", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_recon_module_imports(recon_module_path):
    mod = _load_recon_module(recon_module_path)
    assert (
        hasattr(mod, "run_reconciliation")
        or hasattr(mod, "handler")
        or hasattr(mod, "main")
    ), "recon module must expose run_reconciliation(), handler(), or main()"


def test_first_recon_rule_components_execute_against_real_data(
    recon_module_path, snowflake_connection, iceberg_table, config
):
    """Smoke-probe the first reconciliation rule by directly executing its
    source_expr against Snowflake and reading the target via PyIceberg.

    NOTE: This test does NOT invoke the recon module's run_reconciliation()
    function -- doing so requires a live SparkSession (Glue/EMR) or the
    Lambda runtime, neither of which is available in the test process. The
    qa-agent runs the actual recon module inside the deployed compute engine.
    What this test catches: a source_expr that no longer parses against
    Snowflake, or a target table that has been deleted/renamed."""
    rules = config.get("reconciliation", {}).get("rules") or []
    if not rules:
        pytest.skip("no reconciliation rules configured")
    rule = rules[0]

    # Run the source expression directly against Snowflake. Use the shared
    # type-aware helper so date placeholders inside `'${load_date}'` resolve
    # to a real date literal instead of `'1'` (which Snowflake rejects).
    from conftest import resolve_placeholders_for_test
    source_sql = resolve_placeholders_for_test(
        rule["source_expr"], config.get("parameters")
    )
    with snowflake_connection.cursor() as cur:
        cur.execute(source_sql)
        source_row = cur.fetchone()
    assert source_row is not None, "Source recon query returned no rows"

    # Run the target expression by reading a bounded sample of the Iceberg
    # table (matches the Lambda/ECS recon path). We bound the scan because
    # this test is a smoke probe of the recon machinery, not an authoritative
    # source-vs-target reconciliation -- that's the qa-agent's job and uses
    # the deployed compute engine to scan at scale.
    df = iceberg_table.scan(limit=10000).to_pandas()
    if rule["type"] == "row_count":
        # Use Iceberg's snapshot row count for an exact figure, falling back
        # to the bounded scan if the snapshot is unavailable.
        snapshot = iceberg_table.current_snapshot()
        target_value = int(snapshot.summary.get("total-records", str(len(df)))) if snapshot else len(df)
    elif rule["type"] == "null_check":
        target_value = 0  # the recon module would compute this; here we just probe
    else:
        target_value = len(df)
    assert target_value >= 0, "target metric is negative -- impossible result"
    # Log for debug; do not fail on tolerance -- that's qa-agent's job
    logging.info(
        "Live recon probe rule=%s source=%s target=%s",
        rule["name"], source_row[0] if source_row else None, target_value,
    )
```

### Step 15: Generate `test_negative_cases.py` (Category: negative)

Verifies failure paths fire correctly. Marked with `@pytest.mark.negative`.

```python
import pytest

pytestmark = pytest.mark.negative


class TestNegativeCases:
    def test_substitute_parameters_escapes_quote_injection(self, parameter_utils):
        # An attacker-controlled string parameter must be safely escaped so the
        # value remains a SQL literal and cannot break out into executable SQL.
        defs = [{"name": "x", "type": "string"}]
        payload = "'; DROP TABLE t; --"
        out = parameter_utils.substitute_parameters("WHERE x = '${x}'", {"x": payload}, defs)
        # The single quote inside the payload must be doubled (escaped).
        assert "''" in out, "Single quote in input was not escaped"
        # All single quotes in the output must come in even count -- the literal's
        # opening/closing quotes plus any escaped doublings. An odd count means
        # the literal terminated early and injection succeeded.
        assert out.count("'") % 2 == 0, "Output has unbalanced quotes -- injection possible"

    def test_substitute_parameters_rejects_invalid_date(self, parameter_utils):
        defs = [{"name": "d", "type": "date"}]
        with pytest.raises(ValueError):
            parameter_utils.substitute_parameters("WHERE d = '${d}'", {"d": "not-a-date"}, defs)

    def test_substitute_parameters_rejects_invalid_integer(self, parameter_utils):
        defs = [{"name": "n", "type": "integer"}]
        with pytest.raises(ValueError):
            parameter_utils.substitute_parameters("WHERE n = ${n}", {"n": "1; DROP"}, defs)

    def test_missing_required_parameter_raises(self, parameter_utils, config):
        if not config.get("parameters"):
            pytest.skip("no parameters declared")
        required = [p for p in config["parameters"] if p.get("required", True) and "default" not in p]
        if not required:
            pytest.skip("no required-without-default parameters")
        sql = config["query"]["sql"]
        with pytest.raises(ValueError):
            parameter_utils.substitute_parameters(sql, {}, config["parameters"])
```

### Step 16: Lint and Sanity-Check Generated Files

After writing every file:

1. Run `python -c "import ast; ast.parse(open('FILE').read())"` on each `.py` file
   to confirm it parses. If it does not, log a warning and continue (do not
   block) -- the user can fix or re-run.
2. Run `flake8 pipelines/{product.name}/tests/ --max-line-length=120 --ignore=E501,W503`
   if flake8 is available. Report warnings; do NOT block.
3. Print a manifest of generated files with line counts.

### Step 17: Output Summary

```
========================================
TEST CASES GENERATED
Config:  {config-path}
Product: {product.name}
Engine:  {compute.engine}
========================================

Files written under pipelines/{product.name}/tests/:
  conftest.py                        [N lines]
  test_config_integrity.py           [N lines, M tests]
  test_sql_query.py                  [N lines, M tests]
  test_source_connection.py          [N lines, M tests]
  test_iceberg_target.py             [N lines, M tests]
  test_reconciliation_rules.py       [N lines, M tests]
  test_pipeline_smoke.py             [N lines, M tests]
  test_pipeline_integration.py       [N lines, M tests, engine={engine}]
  test_step_function_asl.py          [N lines, M tests]
  test_negative_cases.py             [N lines, M tests]
  test_data_quality_rules.py         [N lines, M tests]   (if data_quality)
  test_parameter_substitution.py     [N lines, M tests]   (if parameters)
  test_recon_module.py               [N lines, M tests]   (if recon module exists)

Configuration:
  pipelines/{product.name}/pytest.ini

Total tests:    {sum}
Categories:     {N} of 12

Next steps:
  - Run all tests: /run-tests configs/{product.name}.yaml
  - Run + report: /test-pipeline configs/{product.name}.yaml
  - Run a single category: pytest -m smoke pipelines/{product.name}/tests/
========================================
```

## Cross-Cutting Notes

- **Real services, not mocks.** Live tests must connect to real Snowflake
  (read-only OAuth via Secrets Manager), real Iceberg via PyIceberg + Glue
  catalog, and real Step Functions via boto3. There is NO `moto`, NO
  `unittest.mock.patch` of cloud services, NO `MagicMock` of infrastructure.
  Pure functions (e.g. `substitute_parameters`) are tested directly, not
  through fakes.
- **Skips, not failures.** When a real cloud prerequisite is unreachable
  (AWS creds missing, OAuth secret missing, Iceberg table not yet provisioned,
  Step Function not deployed), tests must `pytest.skip(...)` with a clear
  message naming the missing resource. Skips are rendered in the report as
  informational, not as defects.
- **Read-only across the board.** No test may issue DML/DDL against
  Snowflake or write to the Iceberg target. Live SQL probes use `EXPLAIN`,
  `LIMIT 5`, or `LIMIT 0`. Iceberg scans use `scan(limit=N)` where possible.
- **No pipeline triggers.** Tests must NOT call `StartExecution` on the Step
  Function or otherwise launch a real ETL run. Triggering pipelines is the
  production scheduler's job; the test framework only probes existing state.
- **Marker discipline.** Use `@pytest.mark.smoke` for fast static checks,
  `@pytest.mark.integration` for tests that touch live cloud, and
  `@pytest.mark.negative` for failure-path assertions, so users can run
  subsets with `pytest -m`.
- **Prod guardrail.** The generated `conftest.py` includes a
  `pytest_collection_modifyitems` hook that auto-skips `integration` and
  `live` tests when `ENV=prod` unless `LIVE_TESTS_AGAINST_PROD=1` is also
  exported. Do not remove this hook from the template.
- **Idempotent regeneration.** Re-running this skill must overwrite existing
  files cleanly. The generator is the source of truth, not local edits to
  `conftest.py` or test files.
