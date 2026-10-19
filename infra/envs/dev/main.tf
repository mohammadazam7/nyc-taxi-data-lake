# The dev environment: one lake bucket with its raw, clean, quarantine, warehouse and
# quality zones, the Glue catalog and crawlers over it, an Athena workgroup, and the
# clean, model and quality stages as Glue jobs.

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
  alert_topic_arn   = var.alert_topic_arn
}
