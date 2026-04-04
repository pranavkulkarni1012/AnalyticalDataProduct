# ──────────────────────────────────────────────────────────────────────────────
# Environment: Dev
# ──────────────────────────────────────────────────────────────────────────────

terraform {
  required_version = ">= 1.5.0"

  backend "s3" {}

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      Team        = var.team
      ManagedBy   = "terraform"
      Project     = "analytical-data-product"
      Product     = var.product_name
    }
  }
}

# ── Data Sources (Platform Layer) ────────────────────────────────────────────

data "aws_ssm_parameter" "vpc_id" {
  name = "/adp/vpc_id"
}

data "aws_ssm_parameter" "subnet_ids" {
  name = "/adp/subnet_ids"
}

data "aws_ssm_parameter" "glue_security_config" {
  name = "/adp/glue_security_config"
}

data "aws_ssm_parameter" "sns_topic_arn" {
  name = "/adp/sns_topic_arn"
}

# ── IAM Module ───────────────────────────────────────────────────────────────

module "iam" {
  source = "../../modules/iam"

  product_name  = var.product_name
  domain        = var.domain
  environment   = var.environment
  s3_bucket_arn = "arn:aws:s3:::${var.artifact_bucket}"
  s3_data_path  = var.s3_data_path
  secrets_arn   = var.snowflake_secret_arn
  tags          = var.tags
}

# ── Glue Job Module (conditional) ────────────────────────────────────────────

module "glue_job" {
  source = "../../modules/glue_job"
  count  = var.compute_engine == "glue" ? 1 : 0

  product_name       = var.product_name
  job_name           = "adp-${var.domain}-${var.product_name}-etl-${var.environment}"
  glue_database_name = "${var.domain}_${var.product_name}_${var.environment}"
  table_name         = var.target_table_name
  s3_path            = var.s3_data_path
  artifact_bucket    = var.artifact_bucket
  job_script_name    = "${var.product_name}_etl.py"
  glue_role_arn      = module.iam.glue_role_arn
  glue_version       = var.glue_version
  worker_type        = var.worker_type
  num_workers        = var.num_workers
  timeout_minutes    = var.timeout_minutes
  extra_py_files     = var.extra_py_files
  extra_jars         = var.extra_jars
  environment        = var.environment
  tags               = var.tags
}

# ── EMR Cluster Module (conditional) ─────────────────────────────────────────

module "emr_cluster" {
  source = "../../modules/emr_cluster"
  count  = var.compute_engine == "emr" ? 1 : 0

  cluster_name      = "adp-${var.domain}-${var.product_name}-${var.environment}"
  mode              = var.emr_mode
  release_label     = var.emr_release_label
  subnet_ids        = split(",", data.aws_ssm_parameter.subnet_ids.value)
  security_group_ids = var.security_group_ids
  s3_log_uri        = "s3://${var.artifact_bucket}/emr-logs/${var.product_name}/"
  service_role_arn  = module.iam.emr_role_arn
  tags              = var.tags
}

# ── ECS Task Module (conditional) ────────────────────────────────────────────

module "ecr" {
  source = "../../modules/ecr"
  count  = var.compute_engine == "ecs" ? 1 : 0

  domain       = var.domain
  product_name = var.product_name
  tags         = var.tags
}

module "ecs_task" {
  source = "../../modules/ecs_task"
  count  = var.compute_engine == "ecs" ? 1 : 0

  task_family        = "adp-${var.domain}-${var.product_name}-${var.environment}"
  container_image    = var.compute_engine == "ecs" ? module.ecr[0].repository_url : ""
  cpu                = var.ecs_cpu
  memory             = var.ecs_memory
  task_role_arn      = module.iam.ecs_task_role_arn
  execution_role_arn = module.iam.ecs_execution_role_arn
  cluster_arn        = var.ecs_cluster_arn
  subnets            = split(",", data.aws_ssm_parameter.subnet_ids.value)
  security_groups    = var.security_group_ids
  log_retention_days = var.log_retention_days
  tags               = var.tags
}

# ── Lambda Module (conditional or for recon) ─────────────────────────────────

module "lambda_recon" {
  source = "../../modules/lambda"
  count  = var.compute_engine == "lambda" || var.enable_recon_lambda ? 1 : 0

  function_name = "adp-${var.product_name}-recon-${var.environment}"
  handler       = "recon_checker.handler"
  runtime       = "python3.11"
  source_dir    = "${path.module}/../../../pipelines/${var.product_name}/lambdas/"
  role_arn      = module.iam.lambda_role_arn
  environment_variables = {
    PRODUCT_NAME = var.product_name
    ENV          = var.environment
    S3_BUCKET    = var.artifact_bucket
  }
  tags = var.tags
}

# ── Step Function Module ─────────────────────────────────────────────────────

module "step_function" {
  source = "../../modules/step_function"

  product_name       = var.product_name
  domain             = var.domain
  state_machine_name = "adp-${var.domain}-${var.product_name}-${var.environment}"
  definition_file    = "${path.module}/../../../pipelines/${var.product_name}/step_functions/${var.product_name}_orchestrator.asl.json"
  glue_job_name      = var.compute_engine == "glue" ? module.glue_job[0].job_name : ""
  lambda_arns        = var.compute_engine == "lambda" || var.enable_recon_lambda ? [module.lambda_recon[0].function_arn] : []
  sns_topic_arn      = data.aws_ssm_parameter.sns_topic_arn.value
  schedule_cron      = var.schedule_cron
  environment        = var.environment
  log_retention_days = var.log_retention_days
  tags               = var.tags
}

# ── Monitoring Module ────────────────────────────────────────────────────────

module "monitoring" {
  source = "../../modules/monitoring"

  product_name        = var.product_name
  domain              = var.domain
  environment         = var.environment
  glue_job_name       = var.compute_engine == "glue" ? module.glue_job[0].job_name : ""
  state_machine_arn   = module.step_function.state_machine_arn
  sns_topic_arn       = data.aws_ssm_parameter.sns_topic_arn.value
  sla_timeout_minutes = var.timeout_minutes
  log_retention_days  = var.log_retention_days
  tags                = var.tags
}
