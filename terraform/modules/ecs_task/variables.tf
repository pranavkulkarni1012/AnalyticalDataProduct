# ──────────────────────────────────────────────────────────────────────────────
# ECS Task Module - Variables
# ──────────────────────────────────────────────────────────────────────────────

variable "task_family" {
  description = "ECS task definition family name"
  type        = string
}

variable "cpu" {
  description = "CPU units for the task (256, 512, 1024, 2048, 4096)"
  type        = number
  default     = 256
}

variable "memory" {
  description = "Memory in MiB for the task (512, 1024, 2048, ...)"
  type        = number
  default     = 512
}

variable "container_image" {
  description = "Docker image URI for the container"
  type        = string
}

variable "container_port" {
  description = "Container port to expose (null if no port needed)"
  type        = number
  default     = null
}

variable "task_role_arn" {
  description = "IAM role ARN for the task"
  type        = string
}

variable "execution_role_arn" {
  description = "IAM execution role ARN for ECS agent"
  type        = string
}

variable "cluster_arn" {
  description = "ARN of the ECS cluster"
  type        = string
}

variable "desired_count" {
  description = "Desired number of running tasks"
  type        = number
  default     = 1
}

variable "subnets" {
  description = "Subnet IDs for the task network configuration"
  type        = list(string)
}

variable "security_groups" {
  description = "Security group IDs for the task"
  type        = list(string)
}

variable "environment_variables" {
  description = "Environment variables for the container"
  type        = map(string)
  default     = {}
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
