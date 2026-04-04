# ──────────────────────────────────────────────────────────────────────────────
# Monitoring Module - Variables
# ──────────────────────────────────────────────────────────────────────────────

variable "product_name" {
  description = "Name of the analytical data product"
  type        = string
}

variable "domain" {
  description = "Business domain (e.g., sales_analytics)"
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

variable "glue_job_name" {
  description = "Glue job name for failure alarm (empty to skip)"
  type        = string
  default     = ""
}

variable "state_machine_arn" {
  description = "Step Function ARN for failure/duration alarms (empty to skip)"
  type        = string
  default     = ""
}

variable "sla_timeout_minutes" {
  description = "SLA timeout in minutes for duration breach alarm"
  type        = number
  default     = 0
}

variable "create_sns_topic" {
  description = "Whether to create a new SNS topic (false to use existing)"
  type        = bool
  default     = false
}

variable "sns_topic_arn" {
  description = "ARN of an existing SNS topic (used when create_sns_topic is false)"
  type        = string
  default     = ""
}

variable "alert_email_addresses" {
  description = "Email addresses to subscribe to alerts"
  type        = list(string)
  default     = []
}

variable "alert_lambda_arns" {
  description = "Map of Lambda ARNs to subscribe to alerts"
  type        = map(string)
  default     = {}
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
