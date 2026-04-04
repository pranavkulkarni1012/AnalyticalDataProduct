# ──────────────────────────────────────────────────────────────────────────────
# Glue Job Module - Outputs
# ──────────────────────────────────────────────────────────────────────────────

output "job_name" {
  description = "Name of the created Glue job"
  value       = aws_glue_job.etl_job.name
}

output "database_name" {
  description = "Name of the Glue Catalog database"
  value       = aws_glue_catalog_database.product_db.name
}
