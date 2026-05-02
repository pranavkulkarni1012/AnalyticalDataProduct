---
name: generate-test-report
description: Aggregates pytest JUnit XML output (and optional coverage XML) into a structured JSON + human-readable markdown test report, categorized by test family. Use as part of /test-pipeline or directly after /run-tests.
argument-hint: "--run-id <uuid> [--junit-xml <path>] [--coverage-xml <path>] [--output-dir <path>]"
allowed-tools: Read Write Bash Glob
---

# Skill: generate-test-report

## Description

Aggregates the raw pytest output (JUnit XML, coverage XML) produced by
`/run-tests` into a structured report. Emits two files:

1. `test-report.json` -- machine-readable, suitable for CI dashboards
2. `test-report.md` -- human-readable, suitable for PR comments and tickets

The report categorizes results by **test family** (config, sql, source, target,
recon, dq, parameters, smoke, integration, step_function, recon_module,
negative) instead of by file or class. Each family rolls up to a single
PASS/FAIL/SKIP line so reviewers can find the broken category in one glance.

## Inputs

`$ARGUMENTS` may contain:
- `--run-id <uuid>` -- required. Used to compute default paths if `--junit-xml`
  and `--output-dir` are not provided.
- `--junit-xml <path>` -- defaults to `artifacts/test/{run_id}/junit-results.xml`
- `--coverage-xml <path>` -- defaults to `artifacts/test/{run_id}/coverage.xml`
  (optional; coverage section is omitted from the report if absent)
- `--output-dir <path>` -- defaults to `artifacts/test/{run_id}/`
- `--config-path <path>` -- optional; if provided, the report includes
  product/engine context.

## Outputs

| File | Format | Purpose |
|------|--------|---------|
| `{output-dir}/test-report.json` | JSON | machine-readable summary |
| `{output-dir}/test-report.md` | Markdown | human-readable summary |

## Steps

### Step 1: Resolve Inputs

1. Parse `$ARGUMENTS` for the four flags above.
2. Verify `--run-id` is present. If not, stop with a clear error.
3. Compute defaults for `--junit-xml`, `--coverage-xml`, `--output-dir`.
4. Verify the JUnit XML file exists. If not, stop -- the report needs raw data.
5. If `--config-path` is provided, read it and extract `product.name`,
   `product.domain`, `compute.engine`. Otherwise leave those fields blank.

### Step 2: Parse JUnit XML

Use Python with the standard library `xml.etree.ElementTree` (no extra deps).
Iterate every `<testcase>` element and capture:

- `classname` (full module + class)
- `name` (test function)
- `time` (duration in seconds)
- Status: `passed` (no children), `failed` (`<failure>` child), `error`
  (`<error>` child), or `skipped` (`<skipped>` child)
- For non-passing cases: capture `message` and `text` (truncate to first 500 chars)

### Step 3: Categorize Each Test

Map each test's source file (derived from `classname`) to a category:

| Filename suffix | Category |
|-----------------|----------|
| `test_config_integrity` | `config` |
| `test_sql_query` | `sql` |
| `test_source_connection` | `source` |
| `test_iceberg_target` | `target` |
| `test_reconciliation_rules` | `recon` |
| `test_data_quality_rules` | `dq` |
| `test_parameter_substitution` | `parameters` |
| `test_pipeline_smoke` | `smoke` |
| `test_pipeline_integration` | `integration` |
| `test_step_function_asl` | `step_function` |
| `test_recon_module` | `recon_module` |
| `test_negative_cases` | `negative` |
| anything else | `other` |

Each category rolls up to:
```json
{
  "name": "config",
  "total": 11,
  "passed": 11,
  "failed": 0,
  "skipped": 0,
  "errors": 0,
  "status": "PASS",  // PASS if failed+errors==0 and total>0; SKIP if total==0 or all skipped; FAIL otherwise
  "duration_seconds": 0.34,
  "failures": [
    {"test_id": "module.Class.method", "message": "...", "text": "..."}
  ]
}
```

### Step 4: Parse Coverage XML (Optional)

If `--coverage-xml` exists, parse the Cobertura XML to extract:

- Overall line coverage percent
- Per-file line coverage (top 5 lowest-coverage files)

Schema for the JSON section:
```json
"coverage": {
  "overall_pct": 87.4,
  "lines_covered": 1234,
  "lines_total": 1412,
  "lowest_files": [
    {"file": "pipelines/generic/glue/iceberg_writer_spark.py", "pct": 62.5}
  ]
}
```

If the XML is missing or unparseable, omit the `coverage` key entirely.

### Step 5: Assemble Overall Status

The overall status is:
- `PASS` if every non-empty category is `PASS` (skipped categories don't count).
- `FAIL` if any category is `FAIL`.
- `NO_TESTS` if every category has `total == 0`.

### Step 6: Write `test-report.json`

```json
{
  "run_id": "...",
  "generated_at": "ISO-8601 UTC",
  "config_path": "...",
  "product_name": "...",
  "product_domain": "...",
  "engine": "glue",
  "overall_status": "PASS",
  "totals": {"total": 87, "passed": 84, "failed": 2, "skipped": 1, "errors": 0},
  "duration_seconds": 12.3,
  "categories": [
    {... see Step 3 ...}
  ],
  "coverage": {... see Step 4 ...},
  "junit_xml": "artifacts/test/{run_id}/junit-results.xml",
  "coverage_xml": "artifacts/test/{run_id}/coverage.xml"
}
```

### Step 7: Write `test-report.md`

The markdown template:

```markdown
# Test Report -- {product_name}

| Field | Value |
|-------|-------|
| Run ID | `{run_id}` |
| Generated | {generated_at} |
| Product | {product_name} |
| Domain | {product_domain} |
| Engine | {engine} |
| Config | `{config_path}` |
| Overall | **{PASS|FAIL|NO_TESTS}** |
| Duration | {duration_seconds}s |
| Coverage | {pct}% (if available) |

## Totals

| Total | Passed | Failed | Skipped | Errors |
|------:|-------:|-------:|--------:|-------:|
| {total} | {passed} | {failed} | {skipped} | {errors} |

## Categories

| # | Category | Status | Total | Passed | Failed | Skipped | Errors | Time |
|---|----------|--------|------:|-------:|-------:|--------:|-------:|-----:|
| 1 | Config Integrity | PASS | 11 | 11 | 0 | 0 | 0 | 0.34s |
| 2 | SQL Query | PASS | 8 | 8 | 0 | 0 | 0 | 0.21s |
| ... |

## Failures

(Section omitted if there are zero failures.)

### {category} :: {test_id}
**Message:**
```
{message}
```
**Trace (truncated):**
```
{text}
```

## Coverage (Top 5 Lowest)

(Section omitted if no coverage data.)

| File | Coverage |
|------|---------:|
| pipelines/generic/glue/iceberg_writer_spark.py | 62.5% |
| ... |

## Re-run Hints

- All categories: `/test-pipeline {config_path}`
- Failed category only: `/test-pipeline {config_path} --categories {failed_categories} --skip-generate`
- Single test: `pytest pipelines/{product_name}/tests/<file>::<test> -v`
```

### Step 8: Console Echo

Print the totals row and the categories table to stdout so the user sees the
result without opening the markdown.

## Error Handling

| Failure | Action |
|---------|--------|
| `--run-id` missing | Stop with usage hint. |
| JUnit XML missing | Stop. The report depends on raw pytest output. |
| JUnit XML malformed | Stop with the parse error. |
| Coverage XML missing | Skip the coverage section silently. |
| Output directory not writable | Stop with the OSError. |
| Zero tests collected | Write a report with `overall_status: NO_TESTS` and a note that the user should re-run `/generate-test-cases`. |
