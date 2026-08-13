output "search_endpoint" { value = "https://${azurerm_search_service.platform.name}.search.windows.net" }
output "openai_endpoint" { value = azurerm_cognitive_account.openai.endpoint }
output "search_service_id" { value = azurerm_search_service.platform.id }
output "openai_account_id" { value = azurerm_cognitive_account.openai.id }
