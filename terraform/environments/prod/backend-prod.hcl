# ──────────────────────────────────────────────────────────────────────────────
# Prod Backend Configuration
# Usage: terraform init -backend-config=backend-prod.hcl
# ──────────────────────────────────────────────────────────────────────────────

bucket         = "adp-terraform-state-prod"
key            = "analytical-data-product/terraform.tfstate"
region         = "us-east-1"
dynamodb_table = "adp-terraform-locks-prod"
encrypt        = true
