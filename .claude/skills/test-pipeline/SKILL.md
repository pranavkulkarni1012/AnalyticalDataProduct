---
name: test-pipeline
description: Orchestrator skill for automated pipeline testing. Generates a pytest suite from the pipeline config and executes it against the REAL deployed environment - real Snowflake (read-only OAuth via Secrets Manager + corporate proxy), real Iceberg target (PyIceberg via Glue catalog), real Step Functions. Produces a structured pass/fail report. Independent entry point - run after /generate-pipeline AND infra deployment. Use when the user wants to verify a pipeline works end-to-end against live services.
argument-hint: "[config-path] [--env dev|test|staging|prod] [--skip-generate] [--skip-run] [--skip-report] [--coverage] [--categories <list>]"
allowed-tools: Read Write Bash Glob Grep Agent
---

# Skill: test-pipeline

## Description

Single entry point for **automated pipeline testing against the deployed
environment**. Reads a pipeline config, generates a tailored pytest suite,
executes it against real Snowflake / real Iceberg / real Step Functions, and
produces a structured report. This skill is the test-time analogue of
`/run-sdlc`: a deterministic orchestrator that owns `run_id`, artifact paths,
and stage handoffs.

**Independence:** This skill is designed to run **after `/generate-pipeline`
and after infra deployment**. It does NOT depend on `/run-sdlc`. A producer can:

```
/generate-pipeline   configs/my_product.yaml    # produces pipeline code
/generate-terraform  configs/my_product.yaml    # produces infra
# (CI/CD deploys infra to dev)
/test-pipeline       configs/my_product.yaml    # this skill -- runs real tests
```

**Real-execution model.** Tests connect to real Snowflake using OAuth from
AWS Secrets Manager, query real Iceberg tables via PyIceberg + the Glue
catalog, and probe Step Functions via boto3. There are no mocks of cloud
infrastructure. Tests skip gracefully (not fail) when a prerequisite is
unreachable.

**Default environment is `dev`.** The orchestrator passes `ENV=dev` to pytest
unless `--env` is specified. The conftest refuses to run integration tests
against `prod` unless `LIVE_TESTS_AGAINST_PROD=1` is also set in the
environment -- a guardrail against accidentally pointing the test suite at
production.

**Distinction from `qa-agent`:** Both touch live data. `qa-agent` is the
post-deploy production-validation workflow that runs the configured
reconciliation/DQ rules and updates Jira. This skill is a broader, on-demand
test suite (12 categories) that can run from any developer's laptop or from CI
without modifying ticket state.

## Why This Skill Exists

Without an orchestrator, the parent conversation must improvise the sequence
(generate -> run -> report) and the artifact paths. This skill makes the test
flow deterministic, repeatable, and re-runnable for individual categories.

## Inputs

`$ARGUMENTS` may contain:
- A config path (e.g., `configs/monthly_revenue.yaml`) -- optional. If omitted,
  scan `configs/*.yaml`. If exactly one exists, use it. If multiple exist, ask
  the user which to test.
- `--skip-generate` -- reuse existing tests in `pipelines/{product}/tests/`
- `--skip-run` -- only generate test files; do not execute pytest
- `--skip-report` -- run pytest but do not produce JSON/markdown summary
- `--coverage` -- enable `pytest-cov` coverage measurement
- `--categories <comma-list>` -- restrict execution to a subset:
  `config,sql,source,target,recon,dq,parameters,smoke,integration,step_function,recon_module,negative`

## Steps

### Step 0: Resolve Config and Initialize Run

1. Parse `$ARGUMENTS`:
   - First non-flag token = config path (if it exists as a file).
   - Otherwise treat it as a product name and check for `configs/{name}.yaml`.
   - If neither resolves, scan `configs/*.yaml`.
2. If multiple configs exist and none was specified, list them and stop.
3. Generate `run_id`:
   ```bash
   python3 -c "import uuid; print(uuid.uuid4())"
   ```
4. Read the config and extract:
   - `product.name`
   - `compute.engine`
   - Whether `parameters`, `data_quality`, and `reconciliation.rules` exist
5. Create the test artifacts directory:
   ```bash
   mkdir -p artifacts/test/{run_id}
   ```
6. Log the run header (see test-agent for format).

### Step 1: Delegate to test-agent

Invoke the **test-agent** subagent with all parsed inputs:

```
Agent(subagent_type="test-agent", prompt="""
Run the full automated test pipeline for the config at {config_path}.

run_id: {run_id}
product_name: {product_name}
engine: {engine}
flags: {parsed flag list, e.g., --coverage --categories smoke,integration}

Steps to execute:
1. Pre-flight /validate-config (stop on errors).
2. /generate-test-cases (unless --skip-generate).
3. /run-tests (unless --skip-run) with the run_id, coverage, and categories flags.
4. /generate-test-report (unless --skip-report) reading the JUnit XML and writing
   test-report.json + test-report.md to artifacts/test/{run_id}/.
5. Present the final summary table.

Do NOT raise on test failures -- failures are the reportable outcome. Only raise
if pytest itself crashes or a skill invocation errors out.
""")
```

### Step 2: Surface Final Outputs

After the agent returns, list the artifacts that were produced:

- `artifacts/test/{run_id}/junit-results.xml`
- `artifacts/test/{run_id}/test-report.json`
- `artifacts/test/{run_id}/test-report.md`
- `artifacts/test/{run_id}/coverage.xml` (if `--coverage`)

If the report indicates **FAIL**, also surface the top 5 failures inline so the
user does not need to open the markdown to see what broke.

## Exit Behavior

- Tests passed: report success, exit normally.
- Tests failed: report the failures clearly, **but do not raise an exception**.
  A test failure is a successful run of the test pipeline -- the user's pipeline
  has bugs, the test framework worked.
- Skill or pytest crashed: report the error and exit non-zero behavior (stop).

## Re-running Subsets

Common follow-up commands the user can run without going through the full skill:

```bash
# Re-run only one category
/test-pipeline configs/my_product.yaml --categories sql,parameters --skip-generate

# Re-run a single test file directly with pytest
pytest pipelines/my_product/tests/test_parameter_substitution.py -v

# Re-run a single test
pytest pipelines/my_product/tests/test_sql_query.py::TestSQLSafety::test_no_dml_keywords -v
```
