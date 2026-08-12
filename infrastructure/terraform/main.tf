locals {
  deploy = var.enable_deployment ? 1 : 0
  name   = "novabank-ai-${var.environment}"
  tags = {
    project             = "enterprise-genai-agent-platform"
    environment         = var.environment
    data-classification = "synthetic-only"
    managed-by          = "terraform"
  }
}

resource "azurerm_resource_group" "platform" {
  count    = local.deploy
  name     = "rg-${local.name}"
  location = var.location
  tags     = local.tags
}

resource "azurerm_virtual_network" "platform" {
  count               = local.deploy
  name                = "vnet-${local.name}"
  location            = azurerm_resource_group.platform[0].location
  resource_group_name = azurerm_resource_group.platform[0].name
  address_space       = ["10.40.0.0/16"]
  tags                = local.tags
}

resource "azurerm_subnet" "aks" {
  count                           = local.deploy
  name                            = "snet-aks"
  resource_group_name             = azurerm_resource_group.platform[0].name
  virtual_network_name            = azurerm_virtual_network.platform[0].name
  address_prefixes                = ["10.40.0.0/22"]
  default_outbound_access_enabled = false
}

resource "azurerm_subnet" "private_endpoints" {
  count                                         = local.deploy
  name                                          = "snet-private-endpoints"
  resource_group_name                           = azurerm_resource_group.platform[0].name
  virtual_network_name                          = azurerm_virtual_network.platform[0].name
  address_prefixes                              = ["10.40.4.0/24"]
  private_endpoint_network_policies             = "Disabled"
  private_link_service_network_policies_enabled = false
  default_outbound_access_enabled               = false
}

resource "azurerm_log_analytics_workspace" "platform" {
  count                        = local.deploy
  name                         = "log-${local.name}"
  location                     = azurerm_resource_group.platform[0].location
  resource_group_name          = azurerm_resource_group.platform[0].name
  sku                          = "PerGB2018"
  retention_in_days            = 30
  daily_quota_gb               = 1
  local_authentication_enabled = false
  internet_ingestion_enabled   = false
  internet_query_enabled       = false
  tags                         = local.tags
}

resource "azurerm_container_registry" "platform" {
  count                         = local.deploy
  name                          = replace("acr${local.name}", "-", "")
  resource_group_name           = azurerm_resource_group.platform[0].name
  location                      = azurerm_resource_group.platform[0].location
  sku                           = "Premium"
  admin_enabled                 = false
  public_network_access_enabled = false
  anonymous_pull_enabled        = false
  export_policy_enabled         = false
  network_rule_bypass_option    = "None"
  # Docker Content Trust is deprecated for ACR; delivery uses Notation signing.
  trust_policy_enabled = false
  tags                 = local.tags
}

resource "azurerm_key_vault" "platform" {
  count                         = local.deploy
  name                          = "kv-${local.name}"
  location                      = azurerm_resource_group.platform[0].location
  resource_group_name           = azurerm_resource_group.platform[0].name
  tenant_id                     = data.azurerm_client_config.current[0].tenant_id
  sku_name                      = "standard"
  rbac_authorization_enabled    = true
  purge_protection_enabled      = true
  soft_delete_retention_days    = 90
  public_network_access_enabled = false
  tags                          = local.tags
}

data "azurerm_client_config" "current" {
  count = local.deploy
}

module "foundation_private_endpoints" {
  count               = local.deploy
  source              = "./modules/private-endpoints"
  name                = local.name
  location            = var.location
  resource_group_name = azurerm_resource_group.platform[0].name
  subnet_id           = azurerm_subnet.private_endpoints[0].id
  virtual_network_id  = azurerm_virtual_network.platform[0].id
  tags                = local.tags
  services = {
    acr = {
      resource_id = azurerm_container_registry.platform[0].id
      subresource = "registry"
      dns_zone    = "privatelink.azurecr.io"
    }
    key_vault = {
      resource_id = azurerm_key_vault.platform[0].id
      subresource = "vault"
      dns_zone    = "privatelink.vaultcore.azure.net"
    }
  }
}

module "compute" {
  count                  = local.deploy
  source                 = "./modules/compute"
  name                   = local.name
  location               = var.location
  resource_group_name    = azurerm_resource_group.platform[0].name
  subnet_id              = azurerm_subnet.aks[0].id
  admin_group_object_ids = var.aks_admin_group_object_ids
  system_node_vm_size    = var.aks_system_node_vm_size
  system_node_count      = var.aks_system_node_count
  tags                   = local.tags
}

module "data" {
  count               = local.deploy
  source              = "./modules/data"
  name                = local.name
  location            = var.location
  resource_group_name = azurerm_resource_group.platform[0].name
  resource_group_id   = azurerm_resource_group.platform[0].id
  tenant_id           = data.azurerm_client_config.current[0].tenant_id
  endpoint_subnet_id  = azurerm_subnet.private_endpoints[0].id
  virtual_network_id  = azurerm_virtual_network.platform[0].id
  tags                = local.tags
}

module "ai" {
  count               = local.deploy
  source              = "./modules/ai"
  name                = local.name
  location            = var.location
  resource_group_name = azurerm_resource_group.platform[0].name
  endpoint_subnet_id  = azurerm_subnet.private_endpoints[0].id
  virtual_network_id  = azurerm_virtual_network.platform[0].id
  tags                = local.tags
}

module "governance" {
  count                      = local.deploy
  source                     = "./modules/governance"
  name                       = local.name
  location                   = var.location
  resource_group_name        = azurerm_resource_group.platform[0].name
  resource_group_id          = azurerm_resource_group.platform[0].id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.platform[0].id
  monthly_budget_gbp         = var.monthly_budget_gbp
  budget_contact_emails      = var.budget_contact_emails
  budget_start               = var.budget_start
  tags                       = local.tags
}

resource "azurerm_user_assigned_identity" "agent" {
  count               = local.deploy
  name                = "id-${local.name}-agent"
  location            = azurerm_resource_group.platform[0].location
  resource_group_name = azurerm_resource_group.platform[0].name
  tags                = local.tags
}

resource "azurerm_federated_identity_credential" "agent" {
  count               = local.deploy
  name                = "fic-${local.name}-agent"
  resource_group_name = azurerm_resource_group.platform[0].name
  parent_id           = azurerm_user_assigned_identity.agent[0].id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = module.compute[0].oidc_issuer_url
  subject             = "system:serviceaccount:agent-platform:agent-platform"
}

resource "azurerm_role_assignment" "aks_acr_pull" {
  count                            = local.deploy
  scope                            = azurerm_container_registry.platform[0].id
  role_definition_name             = "AcrPull"
  principal_id                     = module.compute[0].kubelet_identity_object_id
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "aks_subnet" {
  count                            = local.deploy
  scope                            = azurerm_subnet.aks[0].id
  role_definition_name             = "Network Contributor"
  principal_id                     = module.compute[0].control_plane_identity_principal_id
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "agent_key_vault" {
  count                            = local.deploy
  scope                            = azurerm_key_vault.platform[0].id
  role_definition_name             = "Key Vault Secrets User"
  principal_id                     = azurerm_user_assigned_identity.agent[0].principal_id
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "agent_search" {
  count                            = local.deploy
  scope                            = module.ai[0].search_service_id
  role_definition_name             = "Search Index Data Reader"
  principal_id                     = azurerm_user_assigned_identity.agent[0].principal_id
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "agent_openai" {
  count                            = local.deploy
  scope                            = module.ai[0].openai_account_id
  role_definition_name             = "Cognitive Services OpenAI User"
  principal_id                     = azurerm_user_assigned_identity.agent[0].principal_id
  skip_service_principal_aad_check = true
}
