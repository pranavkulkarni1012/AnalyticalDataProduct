# ──────────────────────────────────────────────────────────────────────────────
# IAM Module
# Creates least-privilege execution roles for Glue, EMR, ECS, Lambda,
# and Step Functions.
# ──────────────────────────────────────────────────────────────────────────────

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name
}

# ── Glue Execution Role ──────────────────────────────────────────────────────

resource "aws_iam_role" "glue" {
  name = "adp-glue-${var.domain}-${var.product_name}-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "glue.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

data "aws_iam_policy_document" "glue" {
  statement {
    sid    = "S3Access"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket"
    ]
    resources = [
      var.s3_bucket_arn,
      "${var.s3_bucket_arn}/*"
    ]
  }

  statement {
    sid    = "GlueCatalog"
    effect = "Allow"
    actions = [
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetTable",
      "glue:GetTables",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:UpdateTable",
      "glue:CreateTable",
      "glue:BatchGetPartition",
      "glue:BatchCreatePartition"
    ]
    resources = [
      "arn:aws:glue:${local.region}:${local.account_id}:catalog",
      "arn:aws:glue:${local.region}:${local.account_id}:database/*",
      "arn:aws:glue:${local.region}:${local.account_id}:table/*/*"
    ]
  }

  statement {
    sid    = "SecretsManager"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue"
    ]
    resources = [var.secrets_arn]
  }

  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws-glue/adp-${var.product_name}-*",
      "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws-glue/adp-${var.product_name}-*:log-stream:*"
    ]
  }
}

resource "aws_iam_role_policy" "glue" {
  name   = "adp-${var.product_name}-glue-policy-${var.environment}"
  role   = aws_iam_role.glue.id
  policy = data.aws_iam_policy_document.glue.json
}

# ── EMR Execution Role ───────────────────────────────────────────────────────

resource "aws_iam_role" "emr" {
  name = "adp-emr-${var.domain}-${var.product_name}-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "elasticmapreduce.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

data "aws_iam_policy_document" "emr" {
  statement {
    sid    = "S3Access"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket"
    ]
    resources = [
      var.s3_bucket_arn,
      "${var.s3_bucket_arn}/*"
    ]
  }

  statement {
    sid    = "GlueCatalog"
    effect = "Allow"
    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:UpdateTable",
      "glue:CreateTable",
      "glue:GetPartitions",
      "glue:BatchCreatePartition"
    ]
    resources = [
      "arn:aws:glue:${local.region}:${local.account_id}:catalog",
      "arn:aws:glue:${local.region}:${local.account_id}:database/*",
      "arn:aws:glue:${local.region}:${local.account_id}:table/*/*"
    ]
  }

  statement {
    sid    = "SecretsManager"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue"
    ]
    resources = [var.secrets_arn]
  }

  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/emr/adp-${var.product_name}-*",
      "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/emr/adp-${var.product_name}-*:log-stream:*"
    ]
  }
}

resource "aws_iam_role_policy" "emr" {
  name   = "adp-${var.product_name}-emr-policy-${var.environment}"
  role   = aws_iam_role.emr.id
  policy = data.aws_iam_policy_document.emr.json
}

# ── ECS Execution Role ───────────────────────────────────────────────────────

resource "aws_iam_role" "ecs_task" {
  name = "adp-ecs-${var.domain}-${var.product_name}-task-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

data "aws_iam_policy_document" "ecs_task" {
  statement {
    sid    = "S3Access"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket"
    ]
    resources = [
      var.s3_bucket_arn,
      "${var.s3_bucket_arn}/*"
    ]
  }

  statement {
    sid    = "SecretsManager"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue"
    ]
    resources = [var.secrets_arn]
  }

  statement {
    sid    = "GlueCatalog"
    effect = "Allow"
    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:UpdateTable",
      "glue:CreateTable"
    ]
    resources = [
      "arn:aws:glue:${local.region}:${local.account_id}:catalog",
      "arn:aws:glue:${local.region}:${local.account_id}:database/*",
      "arn:aws:glue:${local.region}:${local.account_id}:table/*/*"
    ]
  }
}

resource "aws_iam_role_policy" "ecs_task" {
  name   = "adp-${var.product_name}-ecs-task-policy-${var.environment}"
  role   = aws_iam_role.ecs_task.id
  policy = data.aws_iam_policy_document.ecs_task.json
}

# ── ECS Task Execution Role ──────────────────────────────────────────────────

resource "aws_iam_role" "ecs_execution" {
  name = "adp-ecs-${var.domain}-${var.product_name}-exec-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ── Lambda Execution Role ────────────────────────────────────────────────────

resource "aws_iam_role" "lambda" {
  name = "adp-lambda-${var.domain}-${var.product_name}-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/adp-${var.product_name}-*",
      "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/adp-${var.product_name}-*:log-stream:*"
    ]
  }

  statement {
    sid    = "S3Access"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket"
    ]
    resources = [
      var.s3_bucket_arn,
      "${var.s3_bucket_arn}/*"
    ]
  }

  statement {
    sid    = "SecretsManager"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue"
    ]
    resources = [var.secrets_arn]
  }

  statement {
    sid    = "GlueCatalog"
    effect = "Allow"
    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:GetPartitions"
    ]
    resources = [
      "arn:aws:glue:${local.region}:${local.account_id}:catalog",
      "arn:aws:glue:${local.region}:${local.account_id}:database/*",
      "arn:aws:glue:${local.region}:${local.account_id}:table/*/*"
    ]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "adp-${var.product_name}-lambda-policy-${var.environment}"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}
