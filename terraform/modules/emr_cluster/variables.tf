# ──────────────────────────────────────────────────────────────────────────────
# EMR Cluster Module - Variables
# ──────────────────────────────────────────────────────────────────────────────

variable "cluster_name" {
  description = "Name of the EMR cluster or serverless application"
  type        = string
}

variable "mode" {
  description = "Deployment mode: 'serverless' or 'ec2'"
  type        = string
  default     = "serverless"

  validation {
    condition     = contains(["serverless", "ec2"], var.mode)
    error_message = "Mode must be 'serverless' or 'ec2'."
  }
}

variable "release_label" {
  description = "EMR release label (e.g., emr-6.15.0)"
  type        = string
  default     = "emr-6.15.0"
}

variable "applications" {
  description = "List of applications to install on EC2 cluster"
  type        = list(string)
  default     = ["Spark", "Iceberg"]
}

# ── Serverless Configuration ─────────────────────────────────────────────────

variable "serverless_driver_cpu" {
  description = "CPU for serverless driver"
  type        = string
  default     = "2 vCPU"
}

variable "serverless_driver_memory" {
  description = "Memory for serverless driver"
  type        = string
  default     = "4 GB"
}

variable "serverless_executor_count" {
  description = "Initial executor count for serverless"
  type        = number
  default     = 2
}

variable "serverless_executor_cpu" {
  description = "CPU for each serverless executor"
  type        = string
  default     = "2 vCPU"
}

variable "serverless_executor_memory" {
  description = "Memory for each serverless executor"
  type        = string
  default     = "4 GB"
}

variable "serverless_max_cpu" {
  description = "Maximum CPU for serverless auto-scaling"
  type        = string
  default     = "40 vCPU"
}

variable "serverless_max_memory" {
  description = "Maximum memory for serverless auto-scaling"
  type        = string
  default     = "80 GB"
}

variable "serverless_idle_timeout_minutes" {
  description = "Auto-stop idle timeout in minutes"
  type        = number
  default     = 15
}

# ── EC2 Configuration ────────────────────────────────────────────────────────

variable "master_instance_type" {
  description = "EC2 instance type for master node"
  type        = string
  default     = "m5.xlarge"
}

variable "core_instance_type" {
  description = "EC2 instance type for core nodes"
  type        = string
  default     = "m5.xlarge"
}

variable "core_instance_count" {
  description = "Number of core instances"
  type        = number
  default     = 2
}

variable "task_instance_type" {
  description = "EC2 instance type for task nodes (spot)"
  type        = string
  default     = "m5.xlarge"
}

variable "task_instance_count" {
  description = "Number of task instances (0 to disable)"
  type        = number
  default     = 0
}

variable "task_spot_bid_price" {
  description = "Spot bid price for task instances (e.g., '0.10')"
  type        = string
  default     = null
}

variable "service_role_arn" {
  description = "IAM service role ARN for EMR EC2 cluster"
  type        = string
  default     = ""
}

variable "ec2_instance_profile_arn" {
  description = "IAM instance profile ARN for EC2 instances"
  type        = string
  default     = ""
}

variable "configurations_json" {
  description = "JSON string of EMR configurations"
  type        = string
  default     = ""
}

# ── Shared Configuration ─────────────────────────────────────────────────────

variable "s3_log_uri" {
  description = "S3 URI for EMR logs"
  type        = string
  default     = ""
}

variable "subnet_ids" {
  description = "Subnet IDs for network configuration"
  type        = list(string)
  default     = []
}

variable "security_group_ids" {
  description = "Security group IDs for network configuration"
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
