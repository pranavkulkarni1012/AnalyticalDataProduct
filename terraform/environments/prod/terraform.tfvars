# ──────────────────────────────────────────────────────────────────────────────
# Prod Environment - Variable Values
# ──────────────────────────────────────────────────────────────────────────────

aws_region   = "us-east-1"
environment  = "prod"
team         = "data-engineering"

# Product configuration (override per product)
product_name      = "monthly_revenue_by_category"
domain            = "finance"
compute_engine    = "glue"
target_table_name = "monthly_revenue_by_category"

# S3
artifact_bucket = "adp-artifacts-prod"
s3_data_path    = "s3://adp-data-prod/finance/monthly_revenue_by_category/"

# Secrets
snowflake_secret_arn = "arn:aws:secretsmanager:us-east-1:345678901234:secret:adp/snowflake-oauth-prod"

# Glue (prod: higher capacity)
glue_version = "4.0"
worker_type  = "G.2X"
num_workers  = 5

# Timeouts
timeout_minutes = 120

# Logging (prod: long retention)
log_retention_days = 365

# Scheduling (prod: monthly on 1st at 6am UTC)
schedule_cron = "0 6 1 * ? *"

# Feature flags
enable_recon_lambda = true

tags = {
  CostCenter = "data-platform-prod"
}
