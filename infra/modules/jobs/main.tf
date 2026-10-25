# Glue Spark jobs that run the pipeline's clean, model and quality stages in AWS, and,
# when a Redshift workgroup is given, the load stage.
#
# All three jobs run the same entry script with the package wheel installed on top of
# Glue's own PySpark, so the code that runs in AWS is the code that is tested locally.
# The month range is passed per run:
#
#   aws glue start-job-run --job-name <prefix>-clean \
#     --arguments '{"--start":"2024-01","--end":"2024-03"}'

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

locals {
  account_id    = data.aws_caller_identity.current.account_id
  partition     = data.aws_partition.current.partition
  region        = data.aws_region.current.name
  lake_arn      = "arn:${local.partition}:s3:::${var.lake_bucket}"
  artifacts_arn = "arn:${local.partition}:s3:::${var.artifacts_bucket}"

  script_key = "glue/nyc_lake_job.py"
  stages     = toset(concat(["clean", "model", "quality"], var.load == null ? [] : ["load"]))

  # Glue passes these to the entry script on every run; --start and --end come with
  # the run itself.
  common_arguments = {
    "--job-language"                     = "python"
    "--additional-python-modules"        = "s3://${var.artifacts_bucket}/${var.package_wheel_key}"
    "--lake-root"                        = "s3://${var.lake_bucket}"
    "--taxi-type"                        = contains(var.taxi_types, "yellow") ? "yellow" : sort(tolist(var.taxi_types))[0]
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-job-insights"              = "true"
    "--TempDir"                          = "s3://${var.artifacts_bucket}/glue-temp/"
  }

  load_arguments = var.load == null ? {} : {
    "--redshift-workgroup" = var.load.workgroup_name
    "--redshift-database"  = var.load.database_name
  }

  quality_arguments = var.alert_topic_arn == null ? {
    "--alert-sink" = "log"
    } : {
    "--alert-sink"    = "sns"
    "--sns-topic-arn" = var.alert_topic_arn
  }
}

resource "aws_s3_object" "entry_script" {
  bucket = var.artifacts_bucket
  key    = local.script_key
  source = "${path.module}/../../../glue/nyc_lake_job.py"
  etag   = filemd5("${path.module}/../../../glue/nyc_lake_job.py")
  tags   = var.tags
}

resource "aws_glue_job" "stage" {
  for_each = local.stages

  name              = "${var.name_prefix}-${each.key}"
  description       = "NYC taxi lake: ${each.key} stage for one or more months."
  role_arn          = aws_iam_role.stage[each.key].arn
  glue_version      = var.glue_version
  worker_type       = var.worker_type
  number_of_workers = lookup(var.workers, each.key, 2)
  timeout           = var.timeout_minutes
  max_retries       = 0
  tags              = var.tags

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${var.artifacts_bucket}/${aws_s3_object.entry_script.key}"
  }

  # Two runs of the same stage would write the same partitions; let the second fail
  # fast instead of racing the first.
  execution_property {
    max_concurrent_runs = 1
  }

  default_arguments = merge(
    local.common_arguments,
    { "--stage" = each.key },
    each.key == "quality" ? local.quality_arguments : {},
    each.key == "load" ? local.load_arguments : {},
  )
}
