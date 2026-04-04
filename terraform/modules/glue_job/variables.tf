# ──────────────────────────────────────────────────────────────────────────────
# Glue Job Module - Variables
# ──────────────────────────────────────────────────────────────────────────────

variable "product_name" {
  description = "Name of the analytical data product"
  type        = string
}

variable "job_name" {
  description = "Name of the Glue ETL job"
  type        = string
}

variable "glue_database_name" {
  description = "Name of the Glue Catalog database"
  type        = string
}

variable "table_name" {
  description = "Name of the Iceberg table in the Glue Catalog"
  type        = string
}

variable "s3_path" {
  description = "S3 path for the Iceberg table data (e.g., s3://bucket/path/)"
  type        = string
}

variable "artifact_bucket" {
  description = "S3 bucket for job scripts and artifacts"
  type        = string
}

variable "job_script_name" {
  description = "Filename of the Glue ETL script in S3"
  type        = string
}

variable "glue_role_arn" {
  description = "IAM role ARN for the Glue job"
  type        = string
}

variable "glue_version" {
  description = "Glue version (4.0 for Spark 3.3, 3.0 for Spark 3.1)"
  type        = string
  default     = "4.0"
}

variable "worker_type" {
  description = "Glue worker type (G.1X, G.2X, G.025X)"
  type        = string
  default     = "G.1X"
}

variable "num_workers" {
  description = "Number of Glue workers"
  type        = number
  default     = 2
}

variable "timeout_minutes" {
  description = "Job timeout in minutes"
  type        = number
  default     = 60
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
}

variable "extra_py_files" {
  description = "List of extra Python files to include"
  type        = list(string)
  default     = []
}

variable "extra_jars" {
  description = "List of extra JAR files to include"
  type        = list(string)
  default     = []
}

variable "additional_job_parameters" {
  description = "Additional Glue job default arguments"
  type        = map(string)
  default     = {}
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
