---
name: generate-terraform
description: Generates Terraform modules for the analytical data product infrastructure. Use when deploying or updating infra.
argument-hint: "[config-path]"
allowed-tools: Read Grep Glob Write Bash
---

# Skill: generate-terraform

## Description
Generates Terraform modules and environment configurations for the analytical data
product infrastructure. Reads the pipeline config to determine the compute engine
and generates appropriate resources.

## Prerequisites
This skill assumes `/validate-config` has already run and passed, and that the
engine-specific pipeline script has been generated (normally invoked by
`/generate-pipeline` after delegation). If invoked directly, run `/validate-config`
first and ensure the PySpark/Lambda/container artifact exists before applying Terraform.

## Inputs
- Pipeline config YAML path via `$ARGUMENTS`
- If no path provided, scan the `configs/` directory for `.yaml` files

## Generation Steps

### Step 1: Read Config and Determine Resources

1. Read the pipeline config YAML.
2. Extract `compute.engine`, `product.name`, `product.domain`, `target.*`,
   `runtime.*`, and `product.tags`.
3. Determine which engine-specific resources to generate based on `compute.engine`.

### Step 2: Generate Common Resources (All Engines)

Generate Terraform modules for resources required by all engines:

#### Module: `terraform/modules/iam/`
- `main.tf`: IAM execution role with least-privilege policies:
  - S3 read/write for the target data path
  - Glue Catalog access (read/write for Iceberg tables)
  - Secrets Manager read scoped to the product's specific secret:
    `arn:aws:secretsmanager:{region}:{account_id}:secret:adp/snowflake/{connection.account}/oauth*`
    (do NOT use `adp/snowflake/*/oauth` -- the wildcard grants cross-product access)
  - CloudWatch Logs write
  - SNS publish for notifications
  - Use `data "aws_caller_identity" "current" {}` and
    `data "aws_region" "current" {}` to derive account ID and region
    dynamically -- do NOT accept `account_id` as a variable (prevents
    account IDs from being committed to tfvars)
- `variables.tf`: product_name, domain, s3_bucket, environment, tags
- `outputs.tf`: execution_role_arn, execution_role_name

#### Module: `terraform/modules/step_function/`
- `main.tf`: `aws_sfn_state_machine` resource with `definition = file(var.asl_definition_path)`
  (the `definition` argument accepts the ASL content as a string, loaded via `file()`).
  IAM role for Step Functions (`states.amazonaws.com` trust policy) with permissions
  to invoke the engine resource. This role is distinct from the ETL execution role.
  Use `data "aws_caller_identity"` and `data "aws_region"` for ARN construction.
- `variables.tf`: product_name, asl_definition_path, execution_role_arn,
  compute_engine, environment, tags
- `outputs.tf`: state_machine_arn, state_machine_name

#### Module: `terraform/modules/reconciliation_lambda/`
- `main.tf`: `aws_lambda_function` for the reconciliation checker,
  `aws_lambda_layer_version` if needed, CloudWatch log group
- `variables.tf`: product_name, handler, runtime, memory, timeout, environment, tags
- `outputs.tf`: function_arn, function_name

Note: This is a separate module from the ETL Lambda (Step 3). Use a distinct
module path (`reconciliation_lambda/`) to avoid file collisions when
`compute.engine` is `lambda`.

#### Module: `terraform/modules/monitoring/`
- `main.tf`: CloudWatch log groups, metric alarms (job failures, duration),
  SNS topic for notifications, EventBridge rule for scheduling (from
  `product.schedule.cron` if present)
- `variables.tf`: product_name, cron_expression, alarm_thresholds, tags
- `outputs.tf`: sns_topic_arn, log_group_name, eventbridge_rule_arn

### Step 3: Generate Engine-Specific Resources

Based on `compute.engine`:

#### Glue: `terraform/modules/glue_job/`
- `main.tf`:
  - `aws_glue_job` with worker_type, num_workers, glue_version from `runtime.*`
  - `aws_s3_object` to upload the generated PySpark script
  - References to extra_py_files and extra_jars from `runtime.*`
- `variables.tf`: product_name, script_path, worker_type, num_workers,
  glue_version, extra_py_files, extra_jars, execution_role_arn, tags
- `outputs.tf`: glue_job_name, glue_job_arn

#### EMR: `terraform/modules/emr/`
- `main.tf`:
  - If `runtime.emr_mode` is `"serverless"` (default): `aws_emrserverless_application`
    with Spark release, initial/max capacity from `runtime.*`
  - If `runtime.emr_mode` is `"ec2"`: `aws_emr_cluster` with instance types
    from `runtime.*`
  - `aws_s3_object` to upload the PySpark script
  - Use a `var.emr_mode` variable to conditionally create one or the other
    (use `count = var.emr_mode == "serverless" ? 1 : 0` pattern)
- `variables.tf`: product_name, emr_release, emr_mode (default "serverless"),
  instance_types, initial_capacity, max_capacity, execution_role_arn,
  environment, tags
- `outputs.tf`: resource_id (application_id or cluster_id depending on mode),
  resource_arn
  Note: Use a single output name (`resource_id`) with a conditional value
  rather than two named outputs.

#### Lambda: `terraform/modules/etl_lambda/` (ETL Lambda)
- `main.tf`:
  - `aws_lambda_function` for the ETL handler
  - `aws_lambda_layer_version` for dependencies (from requirements.txt)
  - Memory and timeout from `runtime.lambda_memory_mb` and
    `runtime.lambda_timeout_seconds`
  - Include `archive` provider only when this module is used
- `variables.tf`: product_name, handler, runtime, memory_mb,
  timeout_seconds, execution_role_arn, environment, tags
- `outputs.tf`: function_arn, function_name

#### ECS: `terraform/modules/ecs_task/` and `terraform/modules/ecr/`
- `terraform/modules/ecr/`:
  - `main.tf`:
    - `aws_ecr_repository` for the container image with
      `image_scanning_configuration { scan_on_push = true }`
    - `aws_ecr_lifecycle_policy` (keep last 10 images)
  - `variables.tf`: product_name, environment, tags
  - `outputs.tf`: repository_url, repository_arn
- `terraform/modules/ecs_task/`:
  - `main.tf`:
    - `aws_ecs_task_definition` with cpu/memory from `runtime.ecs_cpu`
      and `runtime.ecs_memory`, container definition referencing ECR image
    - `aws_ecs_service` if needed (for scheduled tasks, use EventBridge + ECS RunTask)
    - CloudWatch log group for container logs
  - `variables.tf`: product_name, cpu, memory, ecr_repo_url, cluster_arn,
    execution_role_arn, subnet_ids, security_group_ids, environment, tags
  - `outputs.tf`: task_definition_arn, service_name (if applicable)

### Step 4: Generate Environment Configurations

For each environment (`dev`, `staging`, `prod`):

#### `terraform/environments/{env}/main.tf`
- `terraform` block with required providers: always include `aws`; include
  `archive` only when `compute.engine` is `lambda` (needed for Lambda zip
  packaging). Do NOT include unused providers.
- `provider "aws"` block with region
- Module invocations for all applicable modules, passing environment-specific
  variables (e.g., different worker counts for dev vs prod)
- Pass `environment` variable to all modules for resource naming

#### `terraform/environments/{env}/variables.tf`
- Common variables: aws_region, environment, product_name, domain
- Engine-specific variables matching the module inputs

#### `terraform/environments/{env}/terraform.tfvars`
- Default values for each environment (dev uses ~50% of prod, staging ~75%):
  - **Glue**: dev: num_workers=2, staging: num_workers=5, prod: from config
  - **EMR**: dev: initial_capacity=1, staging: initial_capacity=2, prod: from config
  - **Lambda**: dev: memory_mb=512/timeout=300, staging: memory_mb=1024/timeout=600, prod: from config
  - **ECS**: dev: cpu=256/memory=512, staging: cpu=512/memory=1024, prod: from config
- Do NOT include `account_id` in tfvars (use `data "aws_caller_identity"` instead)

#### `terraform/environments/{env}/backend-{env}.hcl`
- Backend configuration for remote state:
  ```hcl
  bucket         = "adp-terraform-state-{env}"
  key            = "adp/{domain}/{product_name}/terraform.tfstate"
  region         = "us-east-1"
  dynamodb_table = "adp-terraform-locks-{env}"
  encrypt        = true
  ```
- Replace `{env}`, `{domain}`, and `{product_name}` with actual values from the config.
- This file is used by `terraform init -backend-config="backend-{env}.hcl"`.

#### `terraform/environments/.gitignore`
Generate a `.gitignore` file containing:
```
*.tfvars
*.tfvars.json
.terraform/
*.tfstate
*.tfstate.backup
```
Also generate `terraform.tfvars.example` files with placeholder values instead
of real infrastructure identifiers.

### Step 5: Validation

After generating all Terraform files, verify:
- No hardcoded secrets (AWS account IDs, tokens, passwords) in any `.tf` file.
  Account IDs must come from `data "aws_caller_identity"`, not variables.
- All resources include proper tagging (merged `product.tags` + `runtime.tags`
  + `managed_by` + `environment`).
- IAM policies follow least-privilege principle (scoped to specific resources,
  no wildcards on Secrets Manager paths).
- All module references are consistent across environments.
- Each module directory has `main.tf`, `variables.tf`, `outputs.tf`.
- The `runtime.*` fields present in the config match the expected fields for
  `compute.engine`. If required fields are missing, halt and report which
  fields are absent before generating any files.
- Run `terraform fmt -recursive terraform/` to auto-format all generated files.
  Report any formatting issues.

## Module File Conventions

Each module directory must contain exactly three files:
- `main.tf`: Resource definitions
- `variables.tf`: Input variable declarations with descriptions and types
- `outputs.tf`: Output value declarations

Use consistent naming:
- Resource names: `adp-{product.domain}-{product.name}-{resource_type}-{env}`
  The `{env}` segment comes from the `environment` variable passed from the
  environment `main.tf` to each module. All modules must accept an `environment`
  variable.
- Tags: Merge `product.tags` and `runtime.tags` (on key collision, `runtime.tags`
  wins). Always add `managed_by = "terraform"` and `environment = var.environment`.
  Example merged tags block:
  ```hcl
  tags = merge(
    var.tags,
    {
      managed_by  = "terraform"
      environment = var.environment
    }
  )
  ```

## Output Summary

After generation, present:

```
========================================
TERRAFORM MODULES GENERATION COMPLETE
Config: [config-file-path]
Engine: [compute.engine]
========================================

Generated Modules:
  Common:
    - terraform/modules/iam/ (IAM roles and policies)
    - terraform/modules/step_function/ (Step Function state machine)
    - terraform/modules/reconciliation_lambda/ (Reconciliation Lambda)
    - terraform/modules/monitoring/ (CloudWatch, SNS, EventBridge)

  Engine-Specific:
    - terraform/modules/{engine_module}/ (engine resources)

  Environments:
    - terraform/environments/dev/
    - terraform/environments/staging/
    - terraform/environments/prod/

Security:
  - No hardcoded secrets
  - Least-privilege IAM policies
  - Proper tagging on all resources

Next Steps:
  - Review generated Terraform files
  - Run: cd terraform/environments/dev && terraform init && terraform plan
  - Apply to dev first, then staging, then prod
========================================
```
