# ──────────────────────────────────────────────────────────────────────────────
# ECR Module
# Creates an ECR repository with lifecycle policies and scan-on-push.
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_ecr_repository" "repo" {
  name                 = "adp/${var.domain}/${var.product_name}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "cleanup" {
  repository = aws_ecr_repository.repo.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep only the 10 most recent images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
