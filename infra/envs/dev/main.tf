# The dev environment: one lake bucket with its raw, clean, quarantine, warehouse and
# quality zones, the Glue catalog and crawlers over it, an Athena workgroup, the clean,
# model, quality and load stages as Glue jobs, Redshift Serverless for the warehouse,
# and an SNS topic that job failures and data-quality breaches publish to.

locals {
  tags = {
    project     = "nyc-taxi-lake"
    environment = "dev"
    managed-by  = "terraform"
  }

  # Wheel file names use underscores and the version from pyproject.toml.
  package_wheel_key = "wheels/nyc_taxi_lake-${var.package_version}-py3-none-any.whl"
}

module "storage" {
  source = "../../modules/storage"

  name_prefix   = var.name_prefix
  force_destroy = var.force_destroy
}

module "catalog" {
  source = "../../modules/catalog"

  name_prefix           = var.name_prefix
  lake_bucket           = module.storage.lake_bucket
  athena_results_bucket = module.storage.athena_results_bucket
  taxi_types            = var.taxi_types
}

module "jobs" {
  source = "../../modules/jobs"

  name_prefix       = var.name_prefix
  lake_bucket       = module.storage.lake_bucket
  artifacts_bucket  = module.storage.artifacts_bucket
  package_wheel_key = local.package_wheel_key
  taxi_types        = var.taxi_types
  alert_topic_arn   = module.monitoring.alert_topic_arn

  load = {
    workgroup_name = module.warehouse.workgroup_name
    workgroup_arn  = module.warehouse.workgroup_arn
    database_name  = module.warehouse.database_name
  }
}

module "warehouse" {
  source = "../../modules/warehouse"

  name_prefix           = var.name_prefix
  lake_bucket           = module.storage.lake_bucket
  taxi_types            = var.taxi_types
  max_rpu_hours_per_day = var.max_rpu_hours_per_day
  tags                  = local.tags
}

module "monitoring" {
  source = "../../modules/monitoring"

  name_prefix    = var.name_prefix
  glue_job_names = sort(values(module.jobs.job_names))
  alert_emails   = var.alert_emails
  tags           = local.tags
}
