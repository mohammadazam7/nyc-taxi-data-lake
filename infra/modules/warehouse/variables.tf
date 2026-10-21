variable "name_prefix" {
  description = "Prefix for the Redshift Serverless and IAM resource names."
  type        = string
}

variable "lake_bucket" {
  description = "Name of the lake bucket (storage module output). COPY reads the warehouse zone from it."
  type        = string
}

variable "taxi_types" {
  description = "TLC datasets whose warehouse zone the load role may read."
  type        = set(string)
  default     = ["yellow"]
}

variable "database_name" {
  description = "Database created in the namespace."
  type        = string
  default     = "taxi"
}

variable "base_capacity_rpu" {
  description = "Base capacity of the workgroup in Redshift Processing Units. 8 is the smallest AWS allows."
  type        = number
  default     = 8

  validation {
    condition     = var.base_capacity_rpu >= 8 && var.base_capacity_rpu <= 512 && var.base_capacity_rpu % 8 == 0
    error_message = "base_capacity_rpu must be a multiple of 8 between 8 and 512."
  }
}

variable "max_rpu_hours_per_day" {
  description = "Daily compute limit. Past it, queries are refused rather than billed. Null means no limit."
  type        = number
  default     = 4
}

variable "subnet_ids" {
  description = "Private subnets for the workgroup, in at least three availability zones. Empty uses the default VPC."
  type        = list(string)
  default     = []
}

variable "security_group_ids" {
  description = "Security groups for the workgroup's endpoint. Empty uses the VPC's default group."
  type        = list(string)
  default     = []
}

variable "tags" {
  type    = map(string)
  default = {}
}
