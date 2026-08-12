mock_provider "azurerm" {}

run "zero_resource_plan" {
  command = plan

  variables {
    enable_deployment = false
  }

  assert {
    condition = alltrue([
      length(azurerm_resource_group.platform) == 0,
      length(azurerm_virtual_network.platform) == 0,
      length(azurerm_subnet.aks) == 0,
      length(azurerm_subnet.private_endpoints) == 0,
      length(azurerm_log_analytics_workspace.platform) == 0,
      length(azurerm_container_registry.platform) == 0,
      length(azurerm_key_vault.platform) == 0,
      length(azurerm_user_assigned_identity.agent) == 0,
      length(azurerm_federated_identity_credential.agent) == 0,
      length(azurerm_role_assignment.aks_acr_pull) == 0,
      length(azurerm_role_assignment.aks_subnet) == 0,
      length(azurerm_role_assignment.agent_key_vault) == 0,
      length(azurerm_role_assignment.agent_search) == 0,
      length(azurerm_role_assignment.agent_openai) == 0,
      length(module.foundation_private_endpoints) == 0,
      length(module.compute) == 0,
      length(module.data) == 0,
      length(module.ai) == 0,
      length(module.governance) == 0,
    ])
    error_message = "The default configuration must plan zero Azure resources."
  }
}
