---
name: validate-connection
description: Validates Snowflake connection configuration before pipeline generation. Checks OAuth, proxy, role, and account settings. Use before code generation or when connection config changes.
argument-hint: "[config-path]"
allowed-tools: Read Grep Bash
---

# Skill: validate-connection

## Description
Validates Snowflake connection configuration to catch misconfigurations before runtime.
This skill focuses specifically on connection security and compliance -- it verifies that
the source uses OAuth authentication, corporate proxy, read-only roles, and correct
Secrets Manager references.

This skill is complementary to `/validate-config` which checks the full config schema.
Use this skill when connection settings change or before code generation.

## Inputs
- Pipeline config YAML path via `$ARGUMENTS`
- If no path provided, scan the `configs/` directory for `.yaml` files and validate each

## Validation Steps

Execute ALL checks. Collect all errors before reporting (do not stop at the first failure).

All `connection.*` field paths in this skill refer to `source.connection.*` (the single
source connection object in the config).

### Step 1: File Existence and Source Extraction

1. Read the config file at the given path (or from `configs/` directory).
2. Verify the file exists and is valid YAML. If the file cannot be parsed as valid YAML,
   report FAIL immediately and include the parse error message.
3. Extract the `source` object from the config.
4. If `source` is missing, report FAIL immediately.
5. Verify `source` is an object (map) with a `connection` key.
   If it has no `connection` key, report as an ERROR and stop.

### Step 2: Authentication Validation

1. Verify `source.connection.authenticator` is present and equals `oauth`.
2. If `authenticator` is `password`, `keypair`, `externalbrowser`, or any value other than
   `oauth`, report as a CRITICAL error. Only OAuth authentication is permitted.
3. Verify no credential fields exist in the connection (e.g., `password`, `private_key`,
   `private_key_path`, `token`). If found, report as a CRITICAL error.

### Step 3: Proxy Validation

1. If `source.connection.proxy` is present:
   a. `source.connection.proxy.http_proxy` must be non-empty.
   b. `source.connection.proxy.https_proxy` must be non-empty.
   c. Both proxy URLs should match the corporate proxy pattern:
      `http://corporate-proxy.company.com:<port>` (where port is a number).
      Note: both `http_proxy` and `https_proxy` use the `http://` scheme -- HTTPS traffic
      is proxied via HTTP CONNECT, so `http://` is correct for both fields.
      If they do not match, report as a WARNING (the proxy may be valid but non-standard).
2. If `source.connection.proxy` is NOT present:
   Report as a WARNING -- corporate environments typically require proxy configuration.

### Step 4: Account URL Validation

1. `source.connection.account` must be present and non-empty.
2. The account value should follow the `{identifier}.{region}` pattern
   (e.g., `company-prod.us-east-1`, `myorg.eu-west-2`).
   Specifically, it should contain at least one dot (`.`) separating the account identifier
   from the region.
3. If the account value does not contain a dot, report as an ERROR -- it may be missing the
   region identifier.
4. The account value should NOT include `.snowflakecomputing.com` -- that suffix is added
   automatically by the Snowflake connector. If present, report as a WARNING.

### Step 5: Role Name Validation

1. `source.connection.role` must be present and non-empty.
2. The role name should end with `_READER_ROLE` or `_READ_ROLE` (case-insensitive check).
   If it does not match either suffix, report as a WARNING -- the role may be valid but
   does not follow the naming convention for read-only access.
3. **Security check**: If the role name contains any of the following substrings
   (case-insensitive), report as a CRITICAL error:
   - `_WRITER`
   - `_ADMIN`
   - `_OWNER`
   - `_SYSADMIN`
   - `_SECURITYADMIN`
   - `_ACCOUNTADMIN`
   - `_WRITE`
   These role names imply write access, which violates the Snowflake read-only policy.

### Step 6: Warehouse Validation

1. `source.connection.warehouse` must be present and non-empty.
2. If the warehouse name contains `_WRITE` or `_LOAD` (case-insensitive), report as a
   WARNING -- these warehouse names may imply write-oriented workloads.

### Step 7: Secrets Manager Path Validation

1. Verify that the expected Secrets Manager path can be derived from the account:
   `adp/snowflake/{source.connection.account}/oauth`
2. Report the expected Secrets Manager path so the user can verify it exists in AWS
   Secrets Manager.
3. If `source.connection.account` contains `.snowflakecomputing.com`, warn that the
   Secrets Manager path should use the short account identifier (without the suffix).

### Step 8: Query SQL Safety Check

1. Read `query.sql` from the config.
2. Scan the SQL for DML/DDL keywords (case-insensitive):
   `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`
3. If any are found, report as a CRITICAL error -- Snowflake access is READ-ONLY.
4. Verify the SQL starts with `SELECT` or `WITH` (after trimming whitespace).

## Output Format

Present the validation result in this exact structure:

```
========================================
CONNECTION VALIDATION RESULT: [PASS|FAIL]
Config: [config-file-path]
========================================

Errors (N):
  1. [CRITICAL] [field]: Description of the error
  2. [ERROR] [field]: Description of the error

Warnings (N):
  1. [WARN] [field]: Description of the warning

Connection Summary:
  - Account: company-prod.us-east-1  [OK]
  - Authenticator: oauth  [OK]
  - Role: ADP_READER_ROLE  [OK]
  - Warehouse: ANALYTICS_WH  [OK]
  - Proxy: configured  [OK]
  - Secrets Manager path: adp/snowflake/company-prod.us-east-1/oauth  [OK]
  - Query SQL: SELECT/WITH (read-only)  [OK]

Use [OK], [FAIL], or [WARN] markers on each field based on validation results.

Overall:
  - Authentication: OK (OAuth)
  - Proxy: OK (proxy configured)
  - Role: OK (follows read-only convention)
  - Warehouse: OK (read-oriented warehouse)
  - Account: OK (valid format)
  - Query: OK (read-only SQL)
  - Secrets Manager: path to verify
========================================
```

- If there are ANY CRITICAL or ERROR findings, the overall result is **FAIL**.
- Warnings do not cause a FAIL but should be reported for awareness.
- CRITICAL errors indicate security violations (write-capable roles, non-OAuth auth, DML in SQL).
- Omit the Errors section entirely if there are 0 errors.
- Omit the Warnings section entirely if there are 0 warnings.
