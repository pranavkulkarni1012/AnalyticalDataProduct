# ──────────────────────────────────────────────────────────────────────────────
# Step Function Module - Outputs
# ──────────────────────────────────────────────────────────────────────────────

output "state_machine_arn" {
  description = "ARN of the Step Functions state machine"
  value       = aws_sfn_state_machine.orchestrator.arn
}

output "schedule_arn" {
  description = "ARN of the EventBridge schedule (null if not created)"
  value       = var.schedule_cron != "" ? aws_scheduler_schedule.cron[0].arn : null
}
