output "lake_root" {
  description = "Set NYC_LAKE_ROOT to this to run the CLI against the AWS lake."
  value       = module.storage.lake_root
}

output "artifacts_bucket" {
  description = "Upload the package wheel to wheels/ in this bucket before running a job."
  value       = module.storage.artifacts_bucket
}

output "package_wheel_key" {
  description = "Key the Glue jobs expect the wheel at."
  value       = local.package_wheel_key
}

output "glue_databases" {
  value = module.catalog.database_names
}

output "crawlers" {
  description = "Crawlers in the order a pipeline run should start them."
  value       = module.catalog.crawler_names
}

output "athena_workgroup" {
  value = module.catalog.athena_workgroup
}

output "glue_jobs" {
  description = "Glue job name by stage."
  value       = module.jobs.job_names
}

output "state_machine_arn" {
  description = "Start a pipeline run with aws stepfunctions start-execution."
  value       = module.orchestration.state_machine_arn
}

output "redshift_workgroup" {
  description = "Set NYC_LAKE_REDSHIFT_WORKGROUP to this to run nyc-lake load."
  value       = module.warehouse.workgroup_name
}

output "redshift_database" {
  value = module.warehouse.database_name
}

output "alert_topic_arn" {
  value = module.monitoring.alert_topic_arn
}
