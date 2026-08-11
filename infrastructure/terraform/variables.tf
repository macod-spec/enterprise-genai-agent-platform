variable "enable_deployment" {
  description = "Cost safeguard. False creates no Azure resources. Never change without explicit approval."
  type        = bool
  default     = false
}

variable "subscription_id" {
  description = "Target subscription supplied only by an approved plan/deployment workflow."
  type        = string
  default     = ""
  validation {
    condition     = !var.enable_deployment || can(regex("^[0-9a-fA-F-]{36}$", var.subscription_id))
    error_message = "Deployment planning requires a valid Azure subscription ID."
  }
}

variable "deployment_confirmation" {
  description = "Second safeguard required when deployment is deliberately enabled."
  type        = string
  default     = ""
  sensitive   = true
  validation {
    condition     = !var.enable_deployment || var.deployment_confirmation == "I_ACCEPT_AZURE_COSTS"
    error_message = "Deployment requires the explicit cost acknowledgement token."
  }
}

variable "location" {
  type    = string
  default = "uksouth"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "monthly_budget_gbp" {
  type    = number
  default = 50
  validation {
    condition     = var.monthly_budget_gbp > 0 && var.monthly_budget_gbp <= 500
    error_message = "The portfolio budget must remain between GBP 1 and GBP 500."
  }
}

variable "aks_admin_group_object_ids" {
  description = "Entra groups granted AKS administrator access when deployment is enabled."
  type        = list(string)
  default     = []
  validation {
    condition     = !var.enable_deployment || length(var.aks_admin_group_object_ids) > 0
    error_message = "Deployment requires at least one Entra AKS administrator group."
  }
}

variable "budget_contact_emails" {
  description = "Reviewed cost-alert recipients; required only for an enabled deployment."
  type        = list(string)
  default     = []
  validation {
    condition     = !var.enable_deployment || length(var.budget_contact_emails) > 0
    error_message = "Deployment requires at least one budget alert recipient."
  }
}

variable "budget_start" {
  description = "First day of the approved sandbox budget period in RFC3339 format."
  type        = string
  default     = "2026-08-01T00:00:00Z"
}
