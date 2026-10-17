variable "name_prefix" {
  description = "Prefix for Glue, Athena and IAM resource names."
  type        = string
}

variable "lake_bucket" {
  description = "Name of the lake bucket (storage module output)."
  type        = string
}

variable "athena_results_bucket" {
  description = "Name of the bucket for Athena query results (storage module output)."
  type        = string
}

variable "taxi_types" {
  description = "TLC datasets the lake holds. Each gets its own tables."
  type        = set(string)
  default     = ["yellow"]

  validation {
    condition     = length(var.taxi_types) > 0 && alltrue([for t in var.taxi_types : contains(["yellow", "green", "fhv", "fhvhv"], t)])
    error_message = "taxi_types must be a non-empty subset of yellow, green, fhv, fhvhv."
  }
}

variable "athena_bytes_scanned_cutoff" {
  description = "Per-query limit on bytes scanned in the Athena workgroup. A guard against an accidental full scan."
  type        = number
  default     = 10 * 1024 * 1024 * 1024
}

variable "tags" {
  type    = map(string)
  default = {}
}
