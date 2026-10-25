variable "name_prefix" {
  description = "Prefix for the state machine, schedule, rule and IAM resource names."
  type        = string
}

variable "job_names" {
  description = "Glue job name by stage (jobs module output). The state machine runs clean, model, quality and, if present, load, in that order."
  type        = map(string)

  validation {
    condition     = alltrue([for s in ["clean", "model", "quality"] : contains(keys(var.job_names), s)])
    error_message = "job_names needs clean, model and quality entries."
  }

  validation {
    condition     = alltrue([for s in keys(var.job_names) : contains(["clean", "model", "quality", "load"], s)])
    error_message = "job_names may only name the clean, model, quality and load stages."
  }
}

variable "schedule_expression" {
  description = "EventBridge Scheduler expression for the monthly run, in UTC."
  type        = string
  default     = "cron(0 6 5 * ? *)"
}

variable "schedule_enabled" {
  description = "Start the monthly run on schedule. Manual executions work either way."
  type        = bool
  default     = false
}

variable "lag_months" {
  description = "How many months before the scheduled run the processed month is. TLC publishes a month's trips about two months after it ends."
  type        = number
  default     = 2

  validation {
    condition     = var.lag_months >= 0 && var.lag_months == floor(var.lag_months)
    error_message = "lag_months must be a whole number of months, 0 or more."
  }
}

variable "alert_topic_arn" {
  description = "SNS topic failed executions are reported to (monitoring module output)."
  type        = string
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "tags" {
  type    = map(string)
  default = {}
}
