resource "azurerm_application_insights" "platform" {
  name                         = "appi-${var.name}"
  location                     = var.location
  resource_group_name          = var.resource_group_name
  workspace_id                 = var.log_analytics_workspace_id
  application_type             = "web"
  local_authentication_enabled = false
  internet_ingestion_enabled   = false
  internet_query_enabled       = false
  retention_in_days            = 30
  daily_data_cap_in_gb         = 1
  tags                         = var.tags
}

resource "azurerm_monitor_action_group" "cost" {
  name                = "ag-${var.name}-cost"
  resource_group_name = var.resource_group_name
  short_name          = "costalerts"
  tags                = var.tags

  dynamic "email_receiver" {
    for_each = toset(var.budget_contact_emails)
    content {
      name                    = "cost-${email_receiver.key}"
      email_address           = email_receiver.value
      use_common_alert_schema = true
    }
  }
}

resource "azurerm_consumption_budget_resource_group" "platform" {
  name              = "budget-${var.name}"
  resource_group_id = var.resource_group_id
  amount            = var.monthly_budget_gbp
  time_grain        = "Monthly"

  time_period {
    start_date = var.budget_start
  }

  notification {
    enabled        = true
    threshold      = 50
    operator       = "GreaterThanOrEqualTo"
    threshold_type = "Actual"
    contact_emails = var.budget_contact_emails
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThanOrEqualTo"
    threshold_type = "Actual"
    contact_emails = var.budget_contact_emails
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThanOrEqualTo"
    threshold_type = "Forecasted"
    contact_emails = var.budget_contact_emails
  }
}
