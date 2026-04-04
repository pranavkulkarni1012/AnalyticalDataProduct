# ──────────────────────────────────────────────────────────────────────────────
# Monitoring Module
# Creates CloudWatch log groups, metric alarms, SNS topics, and subscriptions.
# ──────────────────────────────────────────────────────────────────────────────

# ── CloudWatch Log Group ─────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "product" {
  name              = "/adp/${var.domain}/${var.product_name}/${var.environment}"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

# ── SNS Topic for Alerts ─────────────────────────────────────────────────────

resource "aws_sns_topic" "alerts" {
  count = var.create_sns_topic ? 1 : 0

  name = "adp-${var.product_name}-alerts-${var.environment}"

  tags = var.tags
}

resource "aws_sns_topic_subscription" "email" {
  for_each = var.create_sns_topic ? toset(var.alert_email_addresses) : toset([])

  topic_arn = aws_sns_topic.alerts[0].arn
  protocol  = "email"
  endpoint  = each.value
}

resource "aws_sns_topic_subscription" "lambda" {
  for_each = var.create_sns_topic ? var.alert_lambda_arns : {}

  topic_arn = aws_sns_topic.alerts[0].arn
  protocol  = "lambda"
  endpoint  = each.value
}

locals {
  sns_topic_arn = var.create_sns_topic ? aws_sns_topic.alerts[0].arn : var.sns_topic_arn
}

# ── Job Failure Alarm ────────────────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "job_failure" {
  count = var.glue_job_name != "" ? 1 : 0

  alarm_name          = "adp-${var.product_name}-job-failure-${var.environment}"
  alarm_description   = "Alarm when ${var.product_name} Glue job fails"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "glue.driver.aggregate.numFailedTasks"
  namespace           = "Glue"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    JobName = var.glue_job_name
  }

  alarm_actions = [local.sns_topic_arn]
  ok_actions    = [local.sns_topic_arn]

  tags = var.tags
}

# ── Step Function Failure Alarm ──────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "sfn_failure" {
  count = var.state_machine_arn != "" ? 1 : 0

  alarm_name          = "adp-${var.product_name}-sfn-failure-${var.environment}"
  alarm_description   = "Alarm when ${var.product_name} Step Function execution fails"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsFailed"
  namespace           = "AWS/States"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    StateMachineArn = var.state_machine_arn
  }

  alarm_actions = [local.sns_topic_arn]
  ok_actions    = [local.sns_topic_arn]

  tags = var.tags
}

# ── Duration Anomaly Alarm ───────────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "duration_breach" {
  count = var.state_machine_arn != "" && var.sla_timeout_minutes > 0 ? 1 : 0

  alarm_name          = "adp-${var.product_name}-duration-breach-${var.environment}"
  alarm_description   = "Alarm when ${var.product_name} execution exceeds SLA of ${var.sla_timeout_minutes} minutes"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionTime"
  namespace           = "AWS/States"
  period              = 300
  statistic           = "Maximum"
  threshold           = var.sla_timeout_minutes * 60 * 1000
  treat_missing_data  = "notBreaching"

  dimensions = {
    StateMachineArn = var.state_machine_arn
  }

  alarm_actions = [local.sns_topic_arn]

  tags = var.tags
}
