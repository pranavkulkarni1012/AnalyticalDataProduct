# ──────────────────────────────────────────────────────────────────────────────
# IAM Module - Variables
# ──────────────────────────────────────────────────────────────────────────────

variable "product_name" {
  description = "Name of the analytical data product"
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
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
