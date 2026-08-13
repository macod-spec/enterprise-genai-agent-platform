variable "name" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "subnet_id" { type = string }
variable "admin_group_object_ids" { type = list(string) }
variable "system_node_vm_size" { type = string }
variable "system_node_count" { type = number }
variable "tags" { type = map(string) }
