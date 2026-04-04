# ──────────────────────────────────────────────────────────────────────────────
# Staging Backend Configuration
# Usage: terraform init -backend-config=backend-staging.hcl
# ──────────────────────────────────────────────────────────────────────────────

bucket         = "adp-terraform-state-staging"
key            = "analytical-data-product/terraform.tfstate"
region         = "us-east-1"
dynamodb_table = "adp-terraform-locks-staging"
encrypt        = true
