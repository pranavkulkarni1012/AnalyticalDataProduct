# AI SDLC Testing Framework

**Version:** 2.0.0 (real-execution)
**Last Updated:** 2026-05-02
**Audience:** data-product producers, platform engineers, CI/CD owners.

This document describes the **automated pipeline testing framework** that ships
with the AI SDLC project. It is a self-contained subsystem composed of one
subagent and four skills, designed to **run independently after
`/generate-pipeline` and after infrastructure deployment**, validating the
deployed pipeline against **real Snowflake**, **real Iceberg**, and
**real Step Functions** -- no mocks of cloud infrastructure.

> **Real-execution model.** Snowflake access is real (read-only OAuth via
> Secrets Manager + corporate proxy). The Iceberg target is queried via real
> PyIceberg + Glue catalog. The Step Function definition is described via
> boto3. Tests skip gracefully (not fail) when a prerequisite is unreachable,
> so the same suite can be run from a developer laptop, from CI, or from an
> ad-hoc shell with the same results.

---

## Table of Contents

1. [Why This Exists](#1-why-this-exists)
2. [What It Tests](#2-what-it-tests)
3. [Where It Fits in the SDLC](#3-where-it-fits-in-the-sdlc)
4. [Components](#4-components)
5. [Prerequisites](#5-prerequisites)
6. [Quick Start](#6-quick-start)
7. [Test Categories](#7-test-categories)
8. [Output Artifacts](#8-output-artifacts)
9. [Running Subsets](#9-running-subsets)
10. [Coverage Measurement](#10-coverage-measurement)
11. [CI Integration](#11-ci-integration)
12. [Distinction from QA Agent](#12-distinction-from-qa-agent)
13. [Safety Guardrails](#13-safety-guardrails)
14. [Extending the Framework](#14-extending-the-framework)
15. [Troubleshooting](#15-troubleshooting)
16. [Quick Reference](#16-quick-reference)

---

## 1. Why This Exists

Before this framework, the `pipeline-generator` agent emitted **placeholder
test stubs** (function signatures with `...` bodies). Producers had three
unattractive options:

1. Write all test bodies by hand for each new product.
2. Skip tests entirely and rely on the `qa-agent` post-deployment workflow.
3. Discover bugs in production.

This framework closes the gap. From a single command -- `/test-pipeline` --
you get:

- A complete, executable pytest suite tailored to your config and engine
- **Real connections** to Snowflake, Iceberg, and Step Functions in the chosen
  environment (default `dev`)
- A structured JSON + Markdown report
- Categorized pass/fail breakdown for triage

It runs **independently**: no Jira ticket, no `/run-sdlc` orchestration. Just a
config, a deployed `dev` environment, and AWS credentials.

---

## 2. What It Tests

12 categories. Most categories have **two test classes**: a `Static` class
(config shape, file content) and a `Live` class (real cloud probe). Live
classes auto-skip when AWS or Snowflake is unreachable.

| # | Category | Validates (Static) | Validates (Live) |
|---|----------|-------------------|------------------|
| 1 | Config Integrity | Required sections, naming, semver, email | -- |
| 2 | SQL Query | Starts with SELECT/WITH, no DML/DDL, FQ table names, sqlparse, parameter consistency | -- |
| 3 | Source Connection | OAuth-only, no creds in config, role pattern, proxy URLs | OAuth secret exists, Snowflake handshake, role matches, **EXPLAIN of query** |
| 4 | Iceberg Target | catalog/format/s3:// scheme, format-version=2, partition_by | Table exists in Glue, location matches, partition spec matches |
| 5 | Reconciliation Rules | At least one rule, names unique, valid types, tolerance, target_expr references target | -- |
| 6 | Data Quality Rules *(if present)* | Required fields, valid types, range params, regex pattern | not_null / unique / range / regex run against the **real Iceberg dataframe** |
| 7 | Parameter Substitution *(if present)* | Static SQL placeholder ↔ declaration consistency | Unit tests on `substitute_parameters()` |
| 8 | Pipeline Smoke | Generic modules import, correlation_id referenced, ENV defaults DEV | -- |
| 9 | Pipeline Integration | -- | Source SQL **runs against Snowflake** (LIMIT 5), Iceberg target queryable, target schema ⊇ SQL columns |
| 10 | Step Function ASL | Valid JSON, StartAt resolves, Resource matches engine, no hardcoded account IDs | State machine **exists in AWS**, definition is valid JSON |
| 11 | Recon Module *(if present)* | Module imports, exposes entry point | First recon rule **runs against real Snowflake + real Iceberg** |
| 12 | Negative Cases | Quote-injection escaping, invalid date/integer rejection, missing-required raises | -- |

---

## 3. Where It Fits in the SDLC

Drop-in stage between Stage 5 (infrastructure deploy) and Stage 6 (qa-agent):

```
1. /run-sdlc SCRUM-123
   ├── Stage 1: Parse Requirements        -> 01-requirements.json
   ├── Stage 2: Generate Spec             -> 02-spec.json
   ├── Stage 3: Generate Config           -> 03-config.yaml
   ├── Stage 4: Generate Pipeline Code    -> pipelines/generic/{engine}/
   └── Stage 5: Deploy Infrastructure     -> AWS resources live in dev

2. /test-pipeline configs/X.yaml --env dev      <-- THIS FRAMEWORK
   ├── /generate-test-cases                     -> 12 test files
   ├── /run-tests                               -> JUnit XML against live dev
   └── /generate-test-report                    -> JSON + Markdown report

3. (Stage 6) qa-agent runs reconciliation + posts to Jira
```

---

## 4. Components

### Subagent

| Name | Purpose |
|------|---------|
| `test-agent` | End-to-end test orchestration: pre-flight validate, generate, run, report |

### Skills

| Slash Command | Role |
|---|---|
| `/test-pipeline` | Orchestrator -- single entry point. Spawns `test-agent`. |
| `/generate-test-cases` | Writes 12 categories of pytest files into `pipelines/{product}/tests/`. |
| `/run-tests` | Executes pytest with JUnit XML, optional coverage, env-aware. |
| `/generate-test-report` | Aggregates JUnit XML into JSON + Markdown report. |

### Data Flow

```
/test-pipeline configs/X.yaml --env dev
   │
   └──> Agent(test-agent)
           │
           ├─[1]─ /validate-config         (pre-flight, static)
           ├─[2]─ /generate-test-cases     (writes tests, idempotent)
           ├─[3]─ /run-tests --env dev     (real cloud probes)
           └─[4]─ /generate-test-report    (aggregates)
```

---

## 5. Prerequisites

### Toolchain

| Tool | Why |
|------|-----|
| Python 3.11+ | All test code |
| pytest, pytest-cov | Test runner + coverage |
| pyyaml, jsonschema, sqlparse | Config + SQL static analysis |
| snowflake-connector-python | Real Snowflake handshake |
| pyiceberg + pyiceberg[glue] | Real Iceberg reads via Glue catalog |
| boto3 | Real Secrets Manager + Step Functions probes |

All declared in `requirements.txt` -- `pip install -r requirements.txt`.

### AWS Access

The shell running `/test-pipeline` must have AWS credentials scoped to the
target environment account:

```bash
export AWS_PROFILE=adp-dev
export AWS_REGION=us-east-1
export ENV=dev               # set by --env flag; default dev
```

Required IAM permissions (read-only):

- `secretsmanager:DescribeSecret`, `secretsmanager:GetSecretValue` on
  `adp/snowflake/*/oauth`
- `glue:GetDatabase`, `glue:GetTable`, `glue:GetPartitions` on the target db
- `s3:GetObject`, `s3:ListBucket` on the target Iceberg bucket
- `states:ListStateMachines`, `states:DescribeStateMachine`

### Snowflake Access

- The OAuth secret must exist at `adp/snowflake/{account}/oauth` in Secrets
  Manager (created by Terraform during deploy).
- The configured role must already exist in Snowflake and have read on the
  source schemas referenced in `query.sql`.
- If the corporate proxy is required, the runner must be on a network where
  the proxy URLs in the config resolve.

### Deployed Pipeline

Live tests need:
- The Iceberg target table created (Terraform provisions it)
- The Step Function state machine deployed (Terraform)
- The OAuth secret created (Terraform)

If any are missing, the corresponding live tests **skip** with a clear
message. The static categories still run.

---

## 6. Quick Start

### One-shot

```bash
# Test the most recently generated pipeline against dev
/test-pipeline

# Specific product, dev environment
/test-pipeline configs/monthly_revenue.yaml --env dev

# With coverage
/test-pipeline configs/monthly_revenue.yaml --env dev --coverage
```

### Step-by-step (advanced)

```bash
/generate-test-cases  configs/monthly_revenue.yaml
/run-tests            configs/monthly_revenue.yaml --env dev --run-id $(uuidgen) --coverage
/generate-test-report --run-id <uuid>
```

### Re-run only failing categories

```bash
/test-pipeline configs/monthly_revenue.yaml \
    --env dev \
    --skip-generate \
    --categories sql,parameters
```

### Direct pytest (after `/generate-test-cases`)

```bash
ENV=dev AWS_PROFILE=adp-dev pytest pipelines/monthly_revenue/tests/ -v

# Skip live cloud tests (only static)
pytest pipelines/monthly_revenue/tests/ -m "not integration"

# Only the live integration tests
pytest pipelines/monthly_revenue/tests/ -m integration
```

---

## 7. Test Categories

| File | Category Key | Always | Marker |
|------|--------------|--------|--------|
| `test_config_integrity.py` | `config` | Yes | -- |
| `test_sql_query.py` | `sql` | Yes | -- |
| `test_source_connection.py` | `source` | Yes | (live class) |
| `test_iceberg_target.py` | `target` | Yes | (live class) |
| `test_reconciliation_rules.py` | `recon` | Yes | -- |
| `test_data_quality_rules.py` | `dq` | If `data_quality.checks` | (live class) |
| `test_parameter_substitution.py` | `parameters` | If `parameters` | -- |
| `test_pipeline_smoke.py` | `smoke` | Yes | `smoke` |
| `test_pipeline_integration.py` | `integration` | Yes | `integration` |
| `test_step_function_asl.py` | `step_function` | Yes | (live class) |
| `test_recon_module.py` | `recon_module` | If recon module exists | `integration` |
| `test_negative_cases.py` | `negative` | Yes | `negative` |

### Markers

| Marker | Run Cost | Use |
|--------|---------|-----|
| `smoke` | Free | static checks against generic modules |
| `integration` | Real Snowflake/Iceberg queries | end-to-end probe |
| `negative` | Free | failure-path assertions |

Run only static categories: `pytest -m "not integration"`. Run only the live
probe: `pytest -m integration`.

---

## 8. Output Artifacts

After a `/test-pipeline` run, `artifacts/test/{run_id}/`:

| File | Producer | Format | Use |
|------|----------|--------|-----|
| `junit-results.xml` | `/run-tests` | JUnit XML | CI dashboards, pytest replay |
| `coverage.xml` | `/run-tests` (if `--coverage`) | Cobertura XML | coverage dashboards |
| `run-summary.json` | `/run-tests` | JSON | exact pytest argv, exit code, totals |
| `test-report.json` | `/generate-test-report` | JSON | machine-readable report |
| `test-report.md` | `/generate-test-report` | Markdown | PR comments, ticket attachments |

`test-report.json` schema is documented in `.claude/skills/generate-test-report/SKILL.md`.

---

## 9. Running Subsets

`--categories` accepts a comma-separated mix of file categories and markers:

| Use case | Command |
|----------|---------|
| Static only (no AWS/Snowflake) | `/test-pipeline X.yaml --categories config,sql,source,target,recon,parameters,negative` |
| Live probe only | `/test-pipeline X.yaml --categories integration,recon_module` |
| Re-run after a fix | `/test-pipeline X.yaml --skip-generate --categories <failed>` |
| Generate, do not execute | `/test-pipeline X.yaml --skip-run` |
| Execute, no aggregated report | `/test-pipeline X.yaml --skip-report` |

---

## 10. Coverage Measurement

`--coverage` enables `pytest-cov` against the **generic pipeline** modules
under `pipelines/generic/{engine}/`. The Cobertura XML and a per-file
"lowest-coverage" table land in the report.

```bash
/test-pipeline configs/monthly_revenue.yaml --env dev --coverage
```

Why generic-pipeline coverage matters: every product shares the same generic
pipeline. A defect in the writer or recon module silently affects every
product.

---

## 11. CI Integration

### Jenkins

Run after the dev deploy completes:

```groovy
stage('Pipeline Tests (dev)') {
    environment {
        ENV = 'dev'
        AWS_PROFILE = 'adp-dev'
    }
    steps {
        sh 'claude --slash "/test-pipeline configs/${PRODUCT_NAME}.yaml --env dev --coverage"'
        archiveArtifacts artifacts: 'artifacts/test/**/*'
        junit 'artifacts/test/**/junit-results.xml'
    }
}
```

### GitHub Actions

```yaml
- name: Run pipeline tests against dev
  env:
    ENV: dev
    AWS_REGION: us-east-1
  run: claude --slash "/test-pipeline configs/${{ matrix.product }}.yaml --env dev --coverage"
- name: Upload report
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: pipeline-test-report
    path: artifacts/test/
```

### Failure Policy

`/test-pipeline` exits 0 even when tests fail (a test failure is a successful
framework run). To fail the CI job on test failure, parse the report:

```bash
python -c "
import json, sys
r = json.load(open('artifacts/test/<run_id>/test-report.json'))
sys.exit(0 if r['overall_status'] == 'PASS' else 1)
"
```

---

## 12. Distinction from QA Agent

| | `test-agent` (this framework) | `qa-agent` |
|---|---|---|
| **When** | On-demand, post-deploy, any environment | Once per Jira ticket, post-deploy |
| **Validates** | 12 categories: config, SQL, source, target, ASL, recon, DQ, parameters, smoke, integration, negative | Reconciliation rules + DQ checks only |
| **Mocks** | None -- real services everywhere | None -- real services |
| **Cloud probes** | Snowflake handshake, Iceberg read, ASL describe | Snowflake source SQL, Iceberg metric, source-vs-target tolerance |
| **Output** | Pytest JUnit, JSON, Markdown report | Validation JSON, Jira comment |
| **Side effects** | None (read-only across the board) | Posts to Jira, transitions ticket |
| **Required** | Config + AWS creds + deployed dev | Config + AWS creds + deployed dev + Jira ticket |

**Both are needed.** The test-agent gives broader coverage and runs anytime.
The qa-agent owns the formal ticket-closure workflow.

---

## 13. Safety Guardrails

This framework hits real cloud services. The following guardrails are baked
into the generated tests and the orchestrator:

1. **Snowflake stays read-only.** The configured role is required to be
   non-write-capable (`/validate-connection` blocks `*_WRITER`, `*_ADMIN`,
   `*_OWNER`, `*_READWRITE`). The generated tests verify the active role
   matches and use only `SELECT` / `EXPLAIN` queries.
2. **No production by default.** `--env` defaults to `dev`. Pointing at
   `prod` skips all integration tests unless `LIVE_TESTS_AGAINST_PROD=1` is
   also set in the shell environment.
3. **No pipeline triggers.** The integration test reads source and target;
   it does NOT invoke `StartExecution` on the Step Function or trigger Glue
   jobs. Pipeline runs are the production schedule's job.
4. **Bounded queries.** Live SQL probes use `LIMIT 5` (data) or `LIMIT 0`
   (schema). Iceberg scans for live probes use `scan(limit=5)` where
   possible.
5. **Skip-on-unreachable.** Missing AWS creds, missing OAuth secret, missing
   Iceberg table, missing Step Function -> tests skip with a clear message
   instead of failing.

---

## 14. Extending the Framework

### Add a new test category

1. Edit `.claude/skills/generate-test-cases/SKILL.md`. Add a step describing
   the new file, what it asserts, conditional generation.
2. Add the category key to the table in this doc, in the orchestrator's
   `--categories` flag, and in `/run-tests` SKILL.md.
3. Update `/generate-test-report` SKILL.md Step 3 mapping table.

### Tighten or relax assertions

Skills are the source of truth. Edit the relevant template, then re-run
`/generate-test-cases` to regenerate -- existing tests are **overwritten**.

### Add a new fixture

Add it to the `conftest.py` template in `generate-test-cases/SKILL.md`
(Step 3). If it varies per engine, document the variance in this file.

---

## 15. Troubleshooting

### "AWS Secrets Manager unreachable"

The session-level `secrets_client` fixture skipped the suite. Check
`AWS_PROFILE`/`AWS_REGION` and that you have `secretsmanager:ListSecrets`.
Run `aws sts get-caller-identity` to confirm.

### "OAuth secret 'adp/snowflake/X/oauth' not retrievable"

Either the secret doesn't exist (Terraform hasn't deployed it for this
environment yet) or the IAM role lacks `secretsmanager:GetSecretValue` on
that ARN.

### "Snowflake connect failed"

Likely causes (in order): (1) corporate proxy not reachable from this host,
(2) OAuth token expired -- re-issue, (3) Snowflake network policy blocks
this source IP, (4) account/warehouse/role mismatch with the secret.

### "Iceberg table {db}.{tbl} not yet created"

Run Terraform apply for the target environment. The table is created during
the first pipeline run; until then, live target tests skip.

### "State machine {name} not deployed to env=dev"

Same: Terraform apply needed. The static ASL tests still run from the local
JSON file.

### "Refusing to run live tests against prod"

By design. Set `LIVE_TESTS_AGAINST_PROD=1` if you genuinely need to.

### "EXPLAIN" fails with a parameter substitution error

The conftest replaces `${param}` placeholders with literal `1` for static
EXPLAIN calls. If your SQL has `${param}` inside a string literal context
(e.g., `'${load_date}'`), the EXPLAIN may fail because `'1'` becomes a
non-date. Either use the parametrized integration test or update the
substitution helper to be type-aware (it already is for the integration
test).

### Tests pass locally but fail in CI

CI typically lacks a corporate proxy. Either route CI through a NAT that can
reach Snowflake, or restrict CI to the static categories
(`--categories config,sql,source,target,recon,parameters,negative`).

---

## 16. Quick Reference

```
/test-pipeline           [config-path] [--env dev|test|staging|prod]
                         [--skip-generate] [--skip-run] [--skip-report]
                         [--coverage] [--categories <list>]

/generate-test-cases     [config-path]

/run-tests               [config-path] [--run-id <uuid>] [--env <env>]
                         [--coverage] [--categories <list>]
                         [--no-fail-on-error]

/generate-test-report    --run-id <uuid> [--junit-xml <path>]
                         [--coverage-xml <path>] [--output-dir <path>]
                         [--config-path <path>]
```

### Categories

```
config, sql, source, target, recon, dq, parameters,
smoke, integration, step_function, recon_module, negative
```

### Required Environment

```
ENV                       dev | test | staging | prod (default dev)
AWS_PROFILE               AWS profile for the target environment
AWS_REGION                defaults to us-east-1
LIVE_TESTS_AGAINST_PROD   set to 1 to allow integration tests against prod (off by default)
MAX_DQ_SCAN_ROWS          DQ live tests skip when target row count > this (default 1_000_000)
```

### Files Produced

```
pipelines/{product}/tests/
  conftest.py                       (real-cloud fixtures)
  pytest.ini
  test_config_integrity.py
  test_sql_query.py
  test_source_connection.py         (Static + Live classes)
  test_iceberg_target.py            (Static + Live classes)
  test_reconciliation_rules.py
  test_data_quality_rules.py        (Static + Live classes, if data_quality)
  test_parameter_substitution.py    (if parameters)
  test_pipeline_smoke.py
  test_pipeline_integration.py      (live cloud probe)
  test_step_function_asl.py         (Static + Live classes)
  test_recon_module.py              (live cloud probe, if recon module)
  test_negative_cases.py

artifacts/test/{run_id}/
  junit-results.xml
  coverage.xml                      (if --coverage)
  run-summary.json
  test-report.json
  test-report.md
```

---

## Getting Help

- Skill source of truth:
  `.claude/skills/{test-pipeline,generate-test-cases,run-tests,generate-test-report}/SKILL.md`
- Agent source of truth: `.claude/agents/test-agent/AGENT.md`
- Project hard constraints: `CLAUDE.md`
- Producer guide (broader SDLC): `instruction.md`
