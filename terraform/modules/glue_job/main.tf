# ──────────────────────────────────────────────────────────────────────────────
# Glue Job Module
# Creates a Glue Catalog database, Iceberg table, and Glue ETL job.
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_glue_catalog_database" "product_db" {
  name        = var.glue_database_name
  description = "Database for ${var.product_name} analytical data product"

  create_table_default_permission {
    permissions = ["ALL"]
    principal {
      data_lake_principal_identifier = "IAM_ALLOWED_PRINCIPALS"
    }
  }
}

resource "aws_glue_catalog_table" "iceberg_table" {
  database_name = aws_glue_catalog_database.product_db.name
  name          = var.table_name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "table_type"        = "ICEBERG"
    "metadata_location" = "${var.s3_path}metadata/"
    "format-version"    = "2"
  }

  open_table_format_input {
    iceberg_input {
      metadata_operation = "CREATE"
      version            = "2"
    }
  }
}

resource "aws_glue_job" "etl_job" {
  name              = var.job_name
  role_arn          = var.glue_role_arn
  glue_version      = var.glue_version
  worker_type       = var.worker_type
  number_of_workers = var.num_workers
  timeout           = var.timeout_minutes
  max_retries       = 1

  command {
    name            = "glueetl"
    script_location = "s3://${var.artifact_bucket}/scripts/${var.product_name}/${var.job_script_name}"
    python_version  = "3"
  }

  default_arguments = merge(
    {
      "--job-language"                     = "python"
      "--enable-continuous-cloudwatch-log" = "true"
      "--enable-metrics"                   = "true"
      "--enable-spark-ui"                  = "true"
      "--spark-event-logs-path"            = "s3://${var.artifact_bucket}/spark-logs/${var.product_name}/"
      "--ENV"                              = var.environment
      "--extra-py-files"                   = join(",", var.extra_py_files)
      "--extra-jars"                       = join(",", var.extra_jars)
      "--conf"                             = "spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog"
    },
    var.additional_job_parameters
  )

  tags = var.tags
}
