# ──────────────────────────────────────────────────────────────────────────────
# Staging Environment - Variable Values
# ──────────────────────────────────────────────────────────────────────────────

aws_region   = "us-east-1"
environment  = "staging"
team         = "data-engineering"

# Product configuration (override per product)
product_name      = "monthly_revenue_by_category"
domain            = "finance"
compute_engine    = "glue"
target_table_name = "monthly_revenue_by_category"

# S3
artifact_bucket = "adp-artifacts-staging"
s3_data_path    = "s3://adp-data-staging/finance/monthly_revenue_by_category/"

# Secrets
snowflake_secret_arn = "arn:aws:secretsmanager:us-east-1:234567890123:secret:adp/snowflake-oauth-staging"

# Glue (staging: moderate capacity)
glue_version = "4.0"
worker_type  = "G.1X"
num_workers  = 3

# Timeouts
timeout_minutes = 60

# Logging (staging: moderate retention)
log_retention_days = 90

# Scheduling
schedule_cron = ""

# Feature flags
enable_recon_lambda = true

tags = {
  CostCenter = "data-platform-staging"
}
