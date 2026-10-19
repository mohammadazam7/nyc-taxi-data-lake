variable "name_prefix" {
  description = "Prefix for Glue job and IAM resource names."
  type        = string
}

variable "lake_bucket" {
  description = "Name of the lake bucket (storage module output)."
  type        = string
}

variable "artifacts_bucket" {
  description = "Name of the bucket holding the job script and the package wheel (storage module output)."
  type        = string
}

variable "package_wheel_key" {
  description = "Key of the nyc-taxi-lake wheel in the artifacts bucket, e.g. wheels/nyc_taxi_lake-0.5.0-py3-none-any.whl."
  type        = string

  validation {
    condition     = endswith(var.package_wheel_key, ".whl")
    error_message = "package_wheel_key must point at a .whl file."
  }
}

variable "taxi_types" {
  description = "TLC datasets the jobs may read and write. The job role is scoped to these prefixes."
  type        = set(string)
  default     = ["yellow"]

  validation {
    condition     = length(var.taxi_types) > 0 && alltrue([for t in var.taxi_types : contains(["yellow", "green", "fhv", "fhvhv"], t)])
    error_message = "taxi_types must be a non-empty subset of yellow, green, fhv, fhvhv."
  }
}

variable "glue_version" {
  description = "AWS Glue version. 5.0 runs Spark 3.5 on Python 3.11."
  type        = string
  default     = "5.0"
}

variable "worker_type" {
  description = "Glue worker type for the Spark jobs."
  type        = string
  default     = "G.1X"
}

variable "workers" {
  description = "Workers per Spark job, by stage. One month of yellow taxi data is roughly 3 million rows."
  type        = map(number)
  default = {
    clean   = 4
    model   = 4
    quality = 2
  }

  validation {
    condition     = alltrue([for s in ["clean", "model", "quality"] : try(var.workers[s] >= 2, false)])
    error_message = "workers needs clean, model and quality entries of at least 2 (Glue's minimum for Spark jobs)."
  }
}

variable "timeout_minutes" {
  description = "Per-run timeout for each job. Glue's default of 48 hours is far too long for a monthly batch."
  type        = number
  default     = 60
}

variable "alert_topic_arn" {
  description = "SNS topic the quality job publishes breaches to. Null keeps alerts in the job log."
  type        = string
  default     = null
}

variable "tags" {
  type    = map(string)
  default = {}
}
