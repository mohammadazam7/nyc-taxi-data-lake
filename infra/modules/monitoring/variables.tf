variable "name_prefix" {
  description = "Prefix for the topic, rule and alarm names."
  type        = string
}

variable "glue_job_names" {
  description = "Glue jobs to watch (jobs module output)."
  type        = list(string)

  validation {
    condition     = length(var.glue_job_names) > 0
    error_message = "glue_job_names must name at least one job."
  }
}

variable "alert_emails" {
  description = "Addresses subscribed to the alert topic. Each one must confirm the subscription from the email AWS sends."
  type        = set(string)
  default     = []
}

variable "failed_task_threshold" {
  description = "Failed Spark tasks in five minutes that raise the alarm. 0 alarms on the first one."
  type        = number
  default     = 0
}

variable "kms_key_arn" {
  description = "Customer managed KMS key for the topic. Null leaves the topic unencrypted; see main.tf."
  type        = string
  default     = null
}

variable "tags" {
  type    = map(string)
  default = {}
}
