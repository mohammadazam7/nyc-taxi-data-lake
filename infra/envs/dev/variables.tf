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

variable "alert_topic_arn" {
  description = "SNS topic for data-quality breaches. Null keeps alerts in the Glue job log until the topic is added in milestone 6."
  type        = string
  default     = null
}

variable "force_destroy" {
  description = "Allow terraform destroy to empty the buckets. Leave false for anything holding data you want to keep."
  type        = bool
  default     = false
}
