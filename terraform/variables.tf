variable "aws_region" {
  description = "AWS region for provisioning"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "production"
}

variable "monthly_budget_usd" {
  description = "Hard budget limit in USD to prevent accidental cloud spend"
  type        = string
  default     = "5.0"
}

variable "alert_email" {
  description = "Notification email for budget alarms"
  type        = string
  default     = "devops-alerts@aegis-enterprise.ai"
}
