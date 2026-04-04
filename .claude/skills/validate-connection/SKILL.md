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
all sources use OAuth authentication, corporate proxy, read-only roles, and correct
Secrets Manager references.

This skill is complementary to `/validate-config` which checks the full config schema.
Use this skill when connection settings change or before code generation.

## Inputs
- Pipeline config YAML path via `$ARGUMENTS`
- If no path provided, scan the `configs/` directory for `.yaml` files and validate each

## Validation Steps

Execute ALL checks for EVERY source in the config. Collect all errors before reporting
(do not stop at the first failure).

All `connection.*` field paths in this skill refer to `sources[i].connection.*` for each
source at index `i` in the `sources` array.

### Step 1: File Existence and Source Extraction

1. Read the config file at the given path (or from `configs/` directory).
2. Verify the file exists and is valid YAML. If the file cannot be parsed as valid YAML,
   report FAIL immediately and include the parse error message.
3. Extract the `sources` array from the config.
4. If `sources` is missing or empty, report FAIL immediately.
5. For each entry in `sources`, verify it is an object (map) with a `connection` key.
   If an entry is not an object or has no `connection` key, report as an ERROR for that
   entry and skip all subsequent connection checks for it.

### Step 2: Authentication Validation

For each source in `sources`:
1. Verify `connection.authenticator` is present and equals `oauth`.
2. If `authenticator` is `password`, `keypair`, `externalbrowser`, or any value other than
   `oauth`, report as a CRITICAL error. Only OAuth authentication is permitted.
3. Verify no credential fields exist in the connection (e.g., `password`, `private_key`,
   `private_key_path`, `token`). If found, report as a CRITICAL error.

### Step 3: Proxy Validation

For each source in `sources`:
1. If `connection.proxy` is present:
   a. `connection.proxy.http_proxy` must be non-empty.
   b. `connection.proxy.https_proxy` must be non-empty.
   c. Both proxy URLs should match the corporate proxy pattern:
      `http://corporate-proxy.company.com:<port>` (where port is a number).
      Note: both `http_proxy` and `https_proxy` use the `http://` scheme -- HTTPS traffic
      is proxied via HTTP CONNECT, so `http://` is correct for both fields.
      If they do not match, report as a WARNING (the proxy may be valid but non-standard).
2. If `connection.proxy` is NOT present:
   Report as a WARNING -- corporate environments typically require proxy configuration.

### Step 4: Account URL Validation

For each source in `sources`:
1. `connection.account` must be present and non-empty.
2. The account value should follow the `{identifier}.{region}` pattern
   (e.g., `company-prod.us-east-1`, `myorg.eu-west-2`).
   Specifically, it should contain at least one dot (`.`) separating the account identifier
   from the region.
3. If the account value does not contain a dot, report as an ERROR -- it may be missing the
   region identifier.
4. The account value should NOT include `.snowflakecomputing.com` -- that suffix is added
   automatically by the Snowflake connector. If present, report as a WARNING.

### Step 5: Role Name Validation

For each source in `sources`:
1. `connection.role` must be present and non-empty.
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

For each source in `sources`:
1. `connection.warehouse` must be present and non-empty.
2. If the warehouse name contains `_WRITE` or `_LOAD` (case-insensitive), report as a
   WARNING -- these warehouse names may imply write-oriented workloads.

### Step 7: Secrets Manager Path Validation

For each source in `sources`:
1. Verify that the expected Secrets Manager path can be derived from the account:
   `adp/snowflake/{connection.account}/oauth`
2. Report the expected Secrets Manager path for each source so the user can verify it
   exists in AWS Secrets Manager.
3. If `connection.account` contains `.snowflakecomputing.com`, warn that the Secrets
   Manager path should use the short account identifier (without the suffix).

### Step 8: Cross-Source Consistency

1. If multiple sources exist, check that all sources use the same `connection.account`.
   If they differ, report as a WARNING -- multiple Snowflake accounts may be intentional
   but is unusual.
2. If multiple sources exist, check that all sources use the same `connection.warehouse`.
   If they differ, report as a WARNING.
3. If multiple sources exist, verify all sources use the same proxy configuration.
   Mismatched proxies across sources may indicate a misconfiguration.
4. If multiple sources exist, verify all sources use the same `connection.authenticator`.
   If they differ, report as a CRITICAL error -- mixed authentication methods indicate a
   misconfiguration and may mean one source bypassed the OAuth requirement.
5. If multiple sources exist, check that all sources use the same `connection.role`.
   If they differ, report as a WARNING -- different roles per source on the same account
   may indicate inconsistent access control.

## Output Format

Present the validation result in this exact structure:

```
========================================
CONNECTION VALIDATION RESULT: [PASS|FAIL]
Config: [config-file-path]
Sources validated: [N]
========================================

Errors (N):
  1. [CRITICAL] [source-name.field]: Description of the error
  2. [ERROR] [source-name.field]: Description of the error

Warnings (N):
  1. [WARN] [source-name.field]: Description of the warning

Per-Source Summary:
  source "customer_orders":
    - Account: company-prod.us-east-1  [OK]
    - Authenticator: oauth  [OK]
    - Role: ADP_READER_ROLE  [OK]
    - Warehouse: ANALYTICS_WH  [OK]
    - Proxy: configured  [OK]
    - Secrets Manager path: adp/snowflake/company-prod.us-east-1/oauth  [OK]

  source "product_catalog":
    - Account: company-prod.us-east-1  [OK]
    - Authenticator: oauth  [OK]
    - Role: ADP_READER_ROLE  [OK]
    - Warehouse: ANALYTICS_WH  [OK]
    - Proxy: configured  [OK]
    - Secrets Manager path: adp/snowflake/company-prod.us-east-1/oauth  [OK]

Use [OK], [FAIL], or [WARN] markers on each field based on validation results.
For example: `Authenticator: password  [FAIL] only oauth is permitted`

Overall:
  - Authentication: OK (all sources use OAuth)
  - Proxy: OK (all sources have proxy configured)
  - Roles: OK (all roles follow read-only convention)
  - Warehouses: OK (all sources use read-oriented warehouses)
  - Accounts: OK (consistent across sources)
  - Cross-source consistency: OK (account, warehouse, proxy, authenticator, role consistent)
  - Secrets Manager: [N] paths to verify
========================================
```

- If there are ANY CRITICAL or ERROR findings, the overall result is **FAIL**.
- Warnings do not cause a FAIL but should be reported for awareness.
- CRITICAL errors indicate security violations (write-capable roles, non-OAuth auth).
- Omit the Errors section entirely if there are 0 errors.
- Omit the Warnings section entirely if there are 0 warnings.
