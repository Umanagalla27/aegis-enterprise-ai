variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment name, used in tags and resource names"
  type        = string
  default     = "production"
}

variable "instance_type" {
  description = "EC2 size. t3.small (2 vCPU, 2 GiB) fits the API + Postgres + Redis + monitoring stack"
  type        = string
  default     = "t3.small"
}

variable "root_volume_gb" {
  description = "Root EBS volume size (Docker images, Postgres and Prometheus data)"
  type        = number
  default     = 30
}

variable "ssh_allowed_cidr" {
  description = "CIDR allowed to SSH, normally your own IP: \"203.0.113.7/32\". Never 0.0.0.0/0"
  type        = string

  validation {
    condition     = can(cidrhost(var.ssh_allowed_cidr, 0)) && var.ssh_allowed_cidr != "0.0.0.0/0"
    error_message = "ssh_allowed_cidr must be a valid CIDR and must not open SSH to the whole internet."
  }
}

variable "ssh_public_key" {
  description = "Public key for the ubuntu user (contents of ~/.ssh/id_ed25519.pub)"
  type        = string
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget; email alerts at 80% (actual) and 100% (forecast)"
  type        = string
  default     = "25"
}

variable "alert_email" {
  description = "Email address that receives budget alerts"
  type        = string
}
