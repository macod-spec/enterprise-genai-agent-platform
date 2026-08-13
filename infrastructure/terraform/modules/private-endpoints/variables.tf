variable "name" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "subnet_id" { type = string }
variable "virtual_network_id" { type = string }
variable "services" {
  type = map(object({
    resource_id = string
    subresource = string
    dns_zone    = string
  }))
}
variable "tags" { type = map(string) }
