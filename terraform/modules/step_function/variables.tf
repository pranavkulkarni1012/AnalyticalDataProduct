# ──────────────────────────────────────────────────────────────────────────────
# Step Function Module - Variables
# ──────────────────────────────────────────────────────────────────────────────

variable "product_name" {
  description = "Name of the analytical data product"
  type        = string
}

variable "state_machine_name" {
  description = "Name of the Step Functions state machine"
  type        = string
}

variable "definition_file" {
  description = "Path to the ASL JSON definition file"
  type        = string
  default     = ""
}

variable "definition_json" {
  description = "Inline ASL JSON definition (takes precedence over definition_file)"
  type        = string
  default     = ""
}

variable "glue_job_name" {
  description = "Glue job name for IAM permissions"
  type        = string
  default     = ""
}

variable "lambda_arns" {
  description = "List of Lambda ARNs the state machine can invoke"
  type        = list(string)
  default     = []
}

variable "sns_topic_arn" {
  description = "SNS topic ARN for notifications"
  type        = string
  default     = ""
}

variable "schedule_cron" {
  description = "Cron expression for EventBridge schedule (empty to disable)"
  type        = string
  default     = ""
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
