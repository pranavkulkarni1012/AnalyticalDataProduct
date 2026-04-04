# ──────────────────────────────────────────────────────────────────────────────
# IAM Module - Outputs
# ──────────────────────────────────────────────────────────────────────────────

output "glue_role_arn" {
  description = "ARN of the Glue execution role"
  value       = aws_iam_role.glue.arn
}

output "emr_role_arn" {
  description = "ARN of the EMR execution role"
  value       = aws_iam_role.emr.arn
}

output "ecs_task_role_arn" {
  description = "ARN of the ECS task role"
  value       = aws_iam_role.ecs_task.arn
}

output "ecs_execution_role_arn" {
  description = "ARN of the ECS task execution role"
  value       = aws_iam_role.ecs_execution.arn
}

output "lambda_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = aws_iam_role.lambda.arn
}
