# ──────────────────────────────────────────────────────────────────────────────
# Lambda Module
# Creates a Lambda function with optional layers and permissions.
# Supports both zip and container image deployment.
# ──────────────────────────────────────────────────────────────────────────────

# ── Lambda Function (Zip Deployment) ─────────────────────────────────────────

data "archive_file" "lambda_zip" {
  count = var.package_type == "Zip" ? 1 : 0

  type        = "zip"
  source_dir  = var.source_dir
  output_path = "${path.module}/.build/${var.function_name}.zip"
}

resource "aws_lambda_function" "function" {
  function_name = var.function_name
  role          = var.role_arn
  timeout       = var.timeout
  memory_size   = var.memory_size
  package_type  = var.package_type

  # Zip deployment
  filename         = var.package_type == "Zip" ? data.archive_file.lambda_zip[0].output_path : null
  source_code_hash = var.package_type == "Zip" ? data.archive_file.lambda_zip[0].output_base64sha256 : null
  handler          = var.package_type == "Zip" ? var.handler : null
  runtime          = var.package_type == "Zip" ? var.runtime : null
  layers           = var.package_type == "Zip" ? var.layer_arns : null

  # Container image deployment
  image_uri = var.package_type == "Image" ? var.image_uri : null

  dynamic "environment" {
    for_each = length(var.environment_variables) > 0 ? [1] : []
    content {
      variables = var.environment_variables
    }
  }

  tags = var.tags
}

# ── Lambda Permission (for invocation by other services) ─────────────────────

resource "aws_lambda_permission" "allow_invocation" {
  for_each = var.allowed_principals

  statement_id  = "Allow${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.function.function_name
  principal     = each.value.service
  source_arn    = each.value.source_arn
}

# ── Optional Lambda Layer ────────────────────────────────────────────────────

resource "aws_lambda_layer_version" "layer" {
  count = var.create_layer ? 1 : 0

  layer_name          = "${var.function_name}-deps"
  filename            = var.layer_zip_path
  compatible_runtimes = [var.runtime]

  description = "Dependencies layer for ${var.function_name}"
}
