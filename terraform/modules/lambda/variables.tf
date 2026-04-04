# ──────────────────────────────────────────────────────────────────────────────
# Lambda Module - Variables
# ──────────────────────────────────────────────────────────────────────────────

variable "function_name" {
  description = "Name of the Lambda function"
  type        = string
}

variable "role_arn" {
  description = "IAM role ARN for the Lambda function"
  type        = string
}

variable "handler" {
  description = "Function handler (e.g., module.handler)"
  type        = string
  default     = "index.handler"
}

variable "runtime" {
  description = "Lambda runtime (e.g., python3.11)"
  type        = string
  default     = "python3.11"
}

variable "timeout" {
  description = "Function timeout in seconds"
  type        = number
  default     = 300
}

variable "memory_size" {
  description = "Function memory in MB"
  type        = number
  default     = 256
}

variable "package_type" {
  description = "Deployment package type: 'Zip' or 'Image'"
  type        = string
  default     = "Zip"

  validation {
    condition     = contains(["Zip", "Image"], var.package_type)
    error_message = "Package type must be 'Zip' or 'Image'."
  }
}

variable "source_dir" {
  description = "Directory containing Lambda source code (for zip deployment)"
  type        = string
  default     = ""
}

variable "image_uri" {
  description = "ECR image URI (for container image deployment)"
  type        = string
  default     = ""
}

variable "layer_arns" {
  description = "List of Lambda layer ARNs to attach"
  type        = list(string)
  default     = []
}

variable "environment_variables" {
  description = "Environment variables for the Lambda function"
  type        = map(string)
  default     = {}
}

variable "allowed_principals" {
  description = "Map of services allowed to invoke this function"
  type = map(object({
    service    = string
    source_arn = string
  }))
  default = {}
}

variable "create_layer" {
  description = "Whether to create a Lambda layer"
  type        = bool
  default     = false
}

variable "layer_zip_path" {
  description = "Path to the layer zip file"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
