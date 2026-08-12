variable "name" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "subnet_id" { type = string }
variable "admin_group_object_ids" { type = list(string) }
variable "tags" { type = map(string) }
