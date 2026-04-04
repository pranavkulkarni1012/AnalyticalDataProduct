# ──────────────────────────────────────────────────────────────────────────────
# ECR Module - Variables
# ──────────────────────────────────────────────────────────────────────────────

variable "domain" {
  description = "Data domain name (e.g., finance, marketing)"
  type        = string
}

variable "product_name" {
  description = "Name of the analytical data product"
  type        = string
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
