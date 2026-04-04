# ──────────────────────────────────────────────────────────────────────────────
# Step Function Module
# Creates a state machine, EventBridge schedule, and execution IAM role.
# ──────────────────────────────────────────────────────────────────────────────

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# ── IAM Role for Step Function Execution ─────────────────────────────────────

resource "aws_iam_role" "sfn_execution" {
  name = "adp-${var.product_name}-sfn-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "sfn_execution" {
  name = "adp-${var.product_name}-sfn-policy-${var.environment}"
  role = aws_iam_role.sfn_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = var.lambda_arns
      },
      {
        Effect = "Allow"
        Action = [
          "glue:StartJobRun",
          "glue:GetJobRun",
          "glue:GetJobRuns",
          "glue:BatchStopJobRun"
        ]
        Resource = "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:job/${var.glue_job_name}"
      },
      {
        Effect = "Allow"
        Action = [
          "ecs:RunTask",
          "ecs:StopTask",
          "ecs:DescribeTasks"
        ]
        Resource = [
          "arn:aws:ecs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:task-definition/adp-${var.product_name}-*",
          "arn:aws:ecs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:task/*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = var.ecs_task_role_arns
      },
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = var.sns_topic_arn
      },
      {
        Effect = "Allow"
        Action = [
          "events:PutTargets",
          "events:PutRule",
          "events:DescribeRule"
        ]
        Resource = "arn:aws:events:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:rule/StepFunctionsGetEventsForECSTaskRule"
      }
    ]
  })
}

# ── State Machine ────────────────────────────────────────────────────────────

resource "aws_sfn_state_machine" "orchestrator" {
  name     = var.state_machine_name
  role_arn = aws_iam_role.sfn_execution.arn

  definition = var.definition_json != "" ? var.definition_json : file(var.definition_file)

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn.arn}:*"
    include_execution_data = true
    level                  = "ERROR"
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "sfn" {
  name              = "/aws/stepfunctions/${var.state_machine_name}"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

# ── EventBridge Scheduler ────────────────────────────────────────────────────

resource "aws_iam_role" "scheduler" {
  count = var.schedule_cron != "" ? 1 : 0

  name = "adp-${var.product_name}-scheduler-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "scheduler.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "scheduler" {
  count = var.schedule_cron != "" ? 1 : 0

  name = "adp-${var.product_name}-scheduler-policy-${var.environment}"
  role = aws_iam_role.scheduler[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "states:StartExecution"
        Resource = aws_sfn_state_machine.orchestrator.arn
      }
    ]
  })
}

resource "aws_scheduler_schedule" "cron" {
  count = var.schedule_cron != "" ? 1 : 0

  name       = "adp-${var.product_name}-schedule-${var.environment}"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "cron(${var.schedule_cron})"

  target {
    arn      = aws_sfn_state_machine.orchestrator.arn
    role_arn = aws_iam_role.scheduler[0].arn
  }
}
