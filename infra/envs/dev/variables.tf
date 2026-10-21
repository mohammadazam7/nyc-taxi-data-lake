variable "region" {
  description = "AWS region for every resource in the environment."
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Prefix for every resource name. Bucket names are global, so include something unique to the account, e.g. \"nyc-lake-dev-1234\"."
  type        = string
}

variable "taxi_types" {
  description = "TLC datasets the lake holds."
  type        = set(string)
  default     = ["yellow"]
}

variable "package_version" {
  description = "Version of the nyc-taxi-lake wheel the Glue jobs install. Upload it first; see infra/README.md."
  type        = string
}

variable "alert_emails" {
  description = "Addresses that receive job failures and data-quality breaches. Each must confirm the subscription."
  type        = set(string)
  default     = []
}

variable "max_rpu_hours_per_day" {
  description = "Daily Redshift Serverless compute limit; queries past it are refused. Null removes the limit."
  type        = number
  default     = 4
}

variable "force_destroy" {
  description = "Allow terraform destroy to empty the buckets. Leave false for anything holding data you want to keep."
  type        = bool
  default     = false
}
