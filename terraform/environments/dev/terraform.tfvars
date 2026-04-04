# ──────────────────────────────────────────────────────────────────────────────
# Dev Environment - Variable Values
# ──────────────────────────────────────────────────────────────────────────────

aws_region   = "us-east-1"
environment  = "dev"
team         = "data-engineering"

# Product configuration (override per product)
product_name     = "monthly_revenue_by_category"
domain           = "finance"
compute_engine   = "glue"
target_table_name = "monthly_revenue_by_category"

# S3
artifact_bucket = "adp-artifacts-dev"
s3_data_path    = "s3://adp-data-dev/finance/monthly_revenue_by_category/"

# Secrets
snowflake_secret_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:adp/snowflake-oauth-dev"

# Glue (dev: smaller capacity)
glue_version = "4.0"
worker_type  = "G.1X"
num_workers  = 2

# Timeouts
timeout_minutes = 30

# Logging (dev: shorter retention)
log_retention_days = 30

# Scheduling (dev: no schedule by default)
schedule_cron = ""

# Feature flags
enable_recon_lambda = true

tags = {
  CostCenter = "data-platform-dev"
}
