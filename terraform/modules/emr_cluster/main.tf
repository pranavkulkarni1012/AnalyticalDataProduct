# ──────────────────────────────────────────────────────────────────────────────
# EMR Cluster Module
# Supports both EMR Serverless and EC2-based deployment modes.
# ──────────────────────────────────────────────────────────────────────────────

# ── EMR Serverless ───────────────────────────────────────────────────────────

resource "aws_emrserverless_application" "serverless" {
  count = var.mode == "serverless" ? 1 : 0

  name          = var.cluster_name
  release_label = var.release_label
  type          = "SPARK"

  initial_capacity {
    initial_capacity_type = "Driver"

    initial_capacity_config {
      worker_count = 1
      worker_configuration {
        cpu    = var.serverless_driver_cpu
        memory = var.serverless_driver_memory
      }
    }
  }

  initial_capacity {
    initial_capacity_type = "Executor"

    initial_capacity_config {
      worker_count = var.serverless_executor_count
      worker_configuration {
        cpu    = var.serverless_executor_cpu
        memory = var.serverless_executor_memory
      }
    }
  }

  maximum_capacity {
    cpu    = var.serverless_max_cpu
    memory = var.serverless_max_memory
  }

  auto_start_configuration {
    enabled = true
  }

  auto_stop_configuration {
    enabled             = true
    idle_timeout_minutes = var.serverless_idle_timeout_minutes
  }

  network_configuration {
    subnet_ids         = var.subnet_ids
    security_group_ids = var.security_group_ids
  }

  tags = var.tags
}

# ── EMR on EC2 ───────────────────────────────────────────────────────────────

resource "aws_emr_cluster" "ec2" {
  count = var.mode == "ec2" ? 1 : 0

  name          = var.cluster_name
  release_label = var.release_label
  applications  = var.applications
  service_role  = var.service_role_arn

  log_uri = var.s3_log_uri

  ec2_attributes {
    instance_profile                  = var.ec2_instance_profile_arn
    subnet_id                         = var.subnet_ids[0]
    emr_managed_master_security_group = length(var.security_group_ids) > 0 ? var.security_group_ids[0] : null
    emr_managed_slave_security_group  = length(var.security_group_ids) > 1 ? var.security_group_ids[1] : null
  }

  master_instance_group {
    instance_type  = var.master_instance_type
    instance_count = 1
  }

  core_instance_group {
    instance_type  = var.core_instance_type
    instance_count = var.core_instance_count
  }

  configurations_json = var.configurations_json != "" ? var.configurations_json : null

  tags = var.tags
}

# ── Optional Task Instance Group (Spot) ──────────────────────────────────────

resource "aws_emr_instance_group" "task" {
  count = var.mode == "ec2" && var.task_instance_count > 0 ? 1 : 0

  cluster_id     = aws_emr_cluster.ec2[0].id
  instance_type  = var.task_instance_type
  instance_count = var.task_instance_count
  name           = "${var.cluster_name}-task"

  bid_price = var.task_spot_bid_price
}
