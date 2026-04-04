# ──────────────────────────────────────────────────────────────────────────────
# Dev Backend Configuration
# Usage: terraform init -backend-config=backend-dev.hcl
# ──────────────────────────────────────────────────────────────────────────────

bucket         = "adp-terraform-state-dev"
key            = "analytical-data-product/terraform.tfstate"
region         = "us-east-1"
dynamodb_table = "adp-terraform-locks-dev"
encrypt        = true
