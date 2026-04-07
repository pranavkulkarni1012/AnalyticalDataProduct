---
name: generate-step-function
description: Generates an AWS Step Function (ASL JSON) that orchestrates the pipeline. Use when creating or updating orchestration.
argument-hint: "[config-path]"
allowed-tools: Read Grep Glob Write Bash
---

# Skill: generate-step-function

## Description
Generates an AWS Step Function state machine definition (ASL JSON) that orchestrates
the analytical data product pipeline. The state machine adapts its resource types
based on `compute.engine` from the config.

## Prerequisites
This skill assumes `/validate-config` has already run and passed (normally invoked by
`/generate-pipeline` before delegation). If invoked directly, run `/validate-config`
first.

## Inputs
- Pipeline config YAML path via `$ARGUMENTS`
- If no path provided, scan the `configs/` directory for `.yaml` files

## Output
- `pipelines/{product.name}/step_functions/{product.name}_orchestrator.asl.json`

## Generation Steps

### Step 1: Read Config

1. Read the pipeline config YAML from `$ARGUMENTS` or `configs/` directory.
2. Extract `compute.engine`, `product.name`, `product.domain`.
3. Derive naming conventions:
   - Job name: `adp-{product.domain}-{product.name}-etl-{env}` (where `{env}` is passed via execution input `$.env`, defaulting to `prod`)
   - Recon Lambda: `adp-{product.name}-recon-{env}`
   - SNS topic: Read from `notifications.sns_topic_arn` in the config if present.
     If absent, use `adp-{product.name}-alerts-{env}` as the topic name and construct
     the ARN as a Terraform variable reference `${var.sns_topic_arn}` to avoid
     hardcoding account IDs or region in the ASL file.

### Step 2: Determine Engine Resource

Map `compute.engine` to the Step Functions resource ARN:
- `glue` -> `arn:aws:states:::glue:startJobRun.sync`
- `emr` -> `arn:aws:states:::elasticmapreduce:addStep.sync` (EMR EC2) or
  `arn:aws:states:::aws-sdk:emrserverless:startJobRun` (EMR Serverless).
  Use EMR Serverless by default; if `runtime.emr_mode` is `"ec2"`, use
  `elasticmapreduce:addStep.sync`. NOTE: EMR Serverless does not support
  the `.sync` optimized integration; use the `aws-sdk` integration and
  add a polling loop (Wait + GetJobRun + Choice) after submission.
- `lambda` -> `arn:aws:states:::lambda:invoke`
- `ecs` -> `arn:aws:states:::ecs:runTask.sync`

### Step 3: Build State Machine

Generate the ASL JSON with the following states:

#### State 1: RunJob

- **Type**: `Task`
- **Resource**: Engine-specific ARN from Step 2
- **Parameters**: Engine-specific parameters. The generic pipeline takes a config path
    as a parameter -- derive it from `$.config_s3_path` in the execution input, or
    default to `s3://{domain}-adp-{env}/configs/{product.name}.yaml`:
  - **Glue**:
    ```json
    {
      "JobName": "{job_name}",
      "Arguments": {
        "--ENV.$": "$.env",
        "--config-path.$": "$.config_s3_path",
        "--JOB_NAME": "{job_name}"
      }
    }
    ```
  - **EMR Serverless**:
    ```json
    {
      "ApplicationId": "{runtime.emr_application_id}",
      "ExecutionRoleArn": "{runtime.execution_role_arn}",
      "JobDriver": {
        "SparkSubmit": {
          "EntryPoint": "s3://{script_s3_path}/{product.name}_etl.py",
          "EntryPointArguments.$": "States.Array('--env', $.env, '--config-path', $.config_s3_path, '--job-name', '{job_name}')",
          "SparkSubmitParameters": "--conf spark.executor.instances=2"
        }
      }
    }
    ```
    Derive `{script_s3_path}` from `compute.script_s3_path` in the config.
    If absent, derive the bucket from `target.s3_path` (strip `s3://`, take the first path segment) and construct as `s3://{bucket}/scripts/{product.name}/`.
    For unresolvable infrastructure placeholders (`emr_application_id`,
    `execution_role_arn`), read from `runtime.*` config keys. If absent,
    emit the literal placeholder string and list each unresolved value in
    the output summary as a warning.
  - **Lambda**:
    ```json
    {
      "FunctionName": "{job_name}",
      "Payload": {
        "env.$": "$.env",
        "config_path.$": "$.config_s3_path"
      }
    }
    ```
  - **ECS**:
    ```json
    {
      "Cluster": "{runtime.ecs_cluster_arn}",
      "TaskDefinition": "{runtime.task_definition_arn}",
      "LaunchType": "FARGATE",
      "Overrides": {
        "ContainerOverrides": [{
          "Name": "{product.name}-container",
          "Command.$": "States.Array('python', 'ecs_entrypoint.py', '--env', $.env, '--config-path', $.config_s3_path)",
          "Environment": [
            {"Name": "CORRELATION_ID", "Value.$": "$.correlation_id"}
          ]
        }]
      },
      "NetworkConfiguration": {
        "AwsvpcConfiguration": {
          "Subnets": ["{runtime.subnet_ids[0]}", "{runtime.subnet_ids[1]}"],
          "AssignPublicIp": "DISABLED"
        }
      }
    }
    ```
    Read `ecs_cluster_arn`, `task_definition_arn`, and `subnet_ids` from
    `runtime.*` config keys. `subnet_ids` is a YAML list -- expand each
    element into its own array entry. If any infrastructure placeholder
    is absent from the config, emit the literal placeholder string and
    list it as an unresolved warning in the output summary.
- **Retry**: 2 retries with exponential backoff:
  ```json
  [
    {
      "ErrorEquals": ["States.TaskFailed"],
      "IntervalSeconds": 30,
      "MaxAttempts": 2,
      "BackoffRate": 2.0
    }
  ]
  ```
  For Glue, add an additional retry for `Glue.ConcurrentRunsExceededException`.
  The specific error must be listed **before** the general `States.TaskFailed`
  entry (ASL processes retries in order, stops at first match):
  ```json
  [
    {
      "ErrorEquals": ["Glue.ConcurrentRunsExceededException"],
      "IntervalSeconds": 60,
      "MaxAttempts": 3,
      "BackoffRate": 2.0
    },
    {
      "ErrorEquals": ["States.TaskFailed"],
      "IntervalSeconds": 30,
      "MaxAttempts": 2,
      "BackoffRate": 2.0
    }
  ]
  ```
- **Catch**: Route all errors to `HandleError`:
  ```json
  [{"ErrorEquals": ["States.ALL"], "Next": "HandleError"}]
  ```
- **Next**: `RunReconciliation`

#### State 2: RunReconciliation

- **Type**: `Task`
- **Resource**: `arn:aws:states:::lambda:invoke`
- **Parameters**:
  ```json
  {
    "FunctionName": "adp-{product.name}-recon-{env}",
    "Payload.$": "$"
  }
  ```
- **ResultSelector**: Extract the Lambda response from the `Payload` envelope
  so downstream states can access fields at `$` directly:
  ```json
  {
    "overall_status.$": "$.Payload.overall_status",
    "rules.$": "$.Payload.rules",
    "correlation_id.$": "$.Payload.correlation_id",
    "run_timestamp.$": "$.Payload.run_timestamp"
  }
  ```
  Note: `arn:aws:states:::lambda:invoke` wraps the Lambda return value under
  `$.Payload`. Without `ResultSelector`, downstream states would need to
  access `$.Payload.overall_status` instead of `$.overall_status`.
- **Retry**: 2 retries for `Lambda.ServiceException` with backoff:
  ```json
  [
    {
      "ErrorEquals": ["Lambda.ServiceException"],
      "IntervalSeconds": 5,
      "MaxAttempts": 2,
      "BackoffRate": 2.0
    }
  ]
  ```
- **Catch**: Route to `HandleError`.
- **Next**: `CheckReconResult`

#### State 3: CheckReconResult

- **Type**: `Choice`
- **Choices**:
  - If `$.overall_status` equals `"PASS"` -> `NotifySuccess`
- **Default**: `NotifyFailure`

#### State 4: NotifySuccess

- **Type**: `Task`
- **Resource**: `arn:aws:states:::sns:publish`
- **Parameters**:
  ```json
  {
    "TopicArn": "{sns_topic_arn}",
    "Subject": "ADP Success: {product.name}",
    "Message.$": "States.Format('Pipeline completed successfully. Reconciliation: {}', $.overall_status)"
  }
  ```
- **End**: `true`

#### State 5: NotifyFailure

- **Type**: `Task`
- **Resource**: `arn:aws:states:::sns:publish`
- **Parameters**:
  ```json
  {
    "TopicArn": "{sns_topic_arn}",
    "Subject": "ADP FAILURE: {product.name}",
    "Message": "Pipeline reconciliation FAILED. Check CloudWatch Logs for details."
  }
  ```
- **Next**: `MarkFailed`

#### State 6: MarkFailed

- **Type**: `Fail`
- **Cause**: `"Reconciliation check failed"`
- **Error**: `"ReconFailure"`

#### State 7: HandleError

- **Type**: `Task`
- **Resource**: `arn:aws:states:::sns:publish`
- **Parameters**:
  ```json
  {
    "TopicArn": "{sns_topic_arn}",
    "Subject": "ADP ERROR: {product.name}",
    "Message": "Pipeline execution error. Check CloudWatch Logs for details."
  }
  ```
  Note: Do NOT expose raw error details (`$.Cause`, `$.Error`) in SNS
  notifications -- they may contain internal resource identifiers, IAM role
  names, or SQL snippets. Use a static, sanitized message and rely on
  CloudWatch Logs for debugging.
- **Next**: `MarkError`

#### State 8: MarkError

- **Type**: `Fail`
- **Cause**: `"Pipeline execution error"`
- **Error**: `"ExecutionError"`

### Step 4: Assemble and Write

1. Assemble all states into a complete ASL JSON document with:
   - `Comment`: `"Orchestrator for {product.name} analytical data product"`
   - `StartAt`: `"RunJob"`
   - `States`: all 8 states above
2. Write to `pipelines/{product.name}/step_functions/{product.name}_orchestrator.asl.json`.
3. Format the JSON with 2-space indentation for readability.

### Step 5: Validate ASL Structure

After writing, verify:
- All `Next` references point to valid state names.
- Every non-terminal state has either `Next` or `End: true`.
- Both `Fail` states have `Cause` and `Error` fields.
- All `Catch` blocks reference existing states.
- Retry configurations have valid `ErrorEquals`, `IntervalSeconds`,
  `MaxAttempts`, and `BackoffRate` fields.

## Output Summary

```
========================================
STEP FUNCTION GENERATION COMPLETE
Config: [config-file-path]
Engine: [compute.engine]
========================================

Generated Files:
  1. pipelines/{product.name}/step_functions/{product.name}_orchestrator.asl.json

State Machine:
  StartAt: RunJob
  States: RunJob -> RunReconciliation -> CheckReconResult
          -> NotifySuccess (PASS) or NotifyFailure -> MarkFailed (FAIL)
          HandleError -> MarkError (on any error)

Engine Resource: [engine-specific ARN]
Retry: 2x with exponential backoff on each task state
Error Handling: Global error catcher -> HandleError -> MarkError

Next Steps:
  - Review ASL definition in pipelines/{product.name}/step_functions/
  - Resolve any unresolved infrastructure placeholders listed above
  - Deploy via AWS Console, CLI, or CloudFormation
  - Run /generate-terraform to provision the Step Function
========================================
```
