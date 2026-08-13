output "postgresql_fqdn" { value = azurerm_postgresql_flexible_server.platform.fqdn }
output "redis_hostname" { value = azurerm_managed_redis.platform.hostname }
