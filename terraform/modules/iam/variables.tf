# ──────────────────────────────────────────────────────────────────────────────
# IAM Module - Variables
# ──────────────────────────────────────────────────────────────────────────────

variable "product_name" {
  description = "Name of the analytical data product"
  type        = string
}

variable "domain" {
  description = "Business domain (e.g., sales_analytics). Used in IAM role naming convention."
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
}

variable "s3_bucket_arn" {
  description = "ARN of the S3 bucket for data and artifacts"
  type        = string
}

variable "s3_data_path" {
  description = "S3 path for data (used in resource-level policies)"
  type        = string
  default     = ""
}

variable "secrets_arn" {
  description = "ARN of the Secrets Manager secret (e.g., Snowflake OAuth)"
  type        = string

  validation {
    condition     = var.secrets_arn == "" || can(regex("^arn:aws:secretsmanager:", var.secrets_arn))
    error_message = "secrets_arn must be empty or a valid Secrets Manager ARN."
  }
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
