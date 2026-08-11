output "cluster_id" { value = azurerm_kubernetes_cluster.platform.id }
output "kubelet_identity_object_id" { value = azurerm_kubernetes_cluster.platform.kubelet_identity[0].object_id }
output "control_plane_identity_principal_id" { value = azurerm_user_assigned_identity.aks.principal_id }
output "oidc_issuer_url" { value = azurerm_kubernetes_cluster.platform.oidc_issuer_url }
