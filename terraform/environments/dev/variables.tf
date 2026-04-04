# ──────────────────────────────────────────────────────────────────────────────
# Environment Variables - Shared across all environments
# ──────────────────────────────────────────────────────────────────────────────

# ── General ──────────────────────────────────────────────────────────────────

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "team" {
  description = "Team name for tagging"
  type        = string
}

variable "product_name" {
  description = "Name of the analytical data product"
  type        = string
}

variable "domain" {
  description = "Data domain (e.g., finance, marketing)"
  type        = string
}

# ── Compute Engine ───────────────────────────────────────────────────────────

variable "compute_engine" {
  description = "Compute engine: glue, emr, lambda, ecs"
  type        = string

  validation {
    condition     = contains(["glue", "emr", "lambda", "ecs"], var.compute_engine)
    error_message = "Compute engine must be glue, emr, lambda, or ecs."
  }
}

# ── S3 & Data ────────────────────────────────────────────────────────────────

variable "artifact_bucket" {
  description = "S3 bucket for artifacts and data"
  type        = string
}

variable "s3_data_path" {
  description = "S3 path for data storage"
  type        = string
}

variable "target_table_name" {
  description = "Target Iceberg table name"
  type        = string
  default     = ""
}

# ── Secrets ──────────────────────────────────────────────────────────────────

variable "snowflake_secret_arn" {
  description = "ARN of the Snowflake OAuth secret in Secrets Manager"
  type        = string
}

# ── Glue Configuration ──────────────────────────────────────────────────────

variable "glue_version" {
  description = "Glue version"
  type        = string
  default     = "4.0"
}

variable "worker_type" {
  description = "Glue worker type"
  type        = string
  default     = "G.1X"
}

variable "num_workers" {
  description = "Number of Glue workers"
  type        = number
  default     = 2
}

variable "extra_py_files" {
  description = "Extra Python files for Glue"
  type        = list(string)
  default     = []
}

variable "extra_jars" {
  description = "Extra JAR files for Glue"
  type        = list(string)
  default     = []
}

# ── EMR Configuration ───────────────────────────────────────────────────────

variable "emr_mode" {
  description = "EMR mode: serverless or ec2"
  type        = string
  default     = "serverless"
}

variable "emr_release_label" {
  description = "EMR release label"
  type        = string
  default     = "emr-6.15.0"
}

# ── ECS Configuration ───────────────────────────────────────────────────────

variable "ecs_cpu" {
  description = "ECS task CPU units"
  type        = number
  default     = 256
}

variable "ecs_memory" {
  description = "ECS task memory in MiB"
  type        = number
  default     = 512
}

variable "ecs_cluster_arn" {
  description = "ARN of the ECS cluster"
  type        = string
  default     = ""
}

# ── Scheduling & Timeouts ───────────────────────────────────────────────────

variable "schedule_cron" {
  description = "Cron expression for scheduled execution"
  type        = string
  default     = ""
}

variable "timeout_minutes" {
  description = "Job timeout in minutes"
  type        = number
  default     = 60
}

# ── Networking ───────────────────────────────────────────────────────────────

variable "security_group_ids" {
  description = "Security group IDs"
  type        = list(string)
  default     = []
}

# ── Feature Flags ────────────────────────────────────────────────────────────

variable "enable_recon_lambda" {
  description = "Enable reconciliation Lambda (independent of compute engine)"
  type        = bool
  default     = true
}

# ── Logging ──────────────────────────────────────────────────────────────────

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

# ── Tags ─────────────────────────────────────────────────────────────────────

variable "tags" {
  description = "Additional resource tags"
  type        = map(string)
  default     = {}
}
