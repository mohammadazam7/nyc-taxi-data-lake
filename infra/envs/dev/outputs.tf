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
