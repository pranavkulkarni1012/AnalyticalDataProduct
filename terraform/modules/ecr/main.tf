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
        description  = "Remove untagged images older than 30 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 30
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Keep only the 10 most recent tagged images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v", "build", "sha"]
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
