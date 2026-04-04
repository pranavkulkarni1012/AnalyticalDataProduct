# ──────────────────────────────────────────────────────────────────────────────
# ECS Task Module - Outputs
# ──────────────────────────────────────────────────────────────────────────────

output "task_definition_arn" {
  description = "ARN of the ECS task definition"
  value       = aws_ecs_task_definition.task.arn
}

output "service_name" {
  description = "Name of the ECS service"
  value       = aws_ecs_service.service.name
}
