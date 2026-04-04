# ──────────────────────────────────────────────────────────────────────────────
# Monitoring Module - Outputs
# ──────────────────────────────────────────────────────────────────────────────

output "log_group_name" {
  description = "Name of the CloudWatch log group"
  value       = aws_cloudwatch_log_group.product.name
}

output "sns_topic_arn" {
  description = "ARN of the SNS alerts topic"
  value       = local.sns_topic_arn
}

output "alarm_arns" {
  description = "ARNs of all CloudWatch alarms"
  value = compact([
    var.glue_job_name != "" ? aws_cloudwatch_metric_alarm.job_failure[0].arn : "",
    var.state_machine_arn != "" ? aws_cloudwatch_metric_alarm.sfn_failure[0].arn : "",
    var.state_machine_arn != "" && var.sla_timeout_minutes > 0 ? aws_cloudwatch_metric_alarm.duration_breach[0].arn : ""
  ])
}
