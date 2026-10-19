variable "name_prefix" {
  description = "Prefix for bucket names, e.g. \"nyc-lake-dev\". Bucket names are global, so include something unique to the account."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{2,40}$", var.name_prefix))
    error_message = "name_prefix must be 3-41 characters of lowercase letters, digits and hyphens."
  }
}

variable "raw_noncurrent_days" {
  description = "Days to keep superseded versions of raw objects. Raw is the only zone that cannot be rebuilt from another, so it is versioned."
  type        = number
  default     = 30
}

variable "raw_glacier_days" {
  description = "Days after which raw objects move to Glacier Instant Retrieval. Raw is read once by the clean job and then only for backfills."
  type        = number
  default     = 90
}

variable "quarantine_expiry_days" {
  description = "Days to keep quarantined rows. Long enough to investigate a bad month, short enough not to pay for them forever."
  type        = number
  default     = 180
}

variable "athena_results_expiry_days" {
  description = "Days to keep Athena query results."
  type        = number
  default     = 7
}

variable "force_destroy" {
  description = "Allow terraform destroy to delete non-empty buckets. Only for throwaway environments."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags added to every bucket."
  type        = map(string)
  default     = {}
}
