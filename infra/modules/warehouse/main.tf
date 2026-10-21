# Redshift Serverless for the warehouse zone: a namespace (the database and its
# storage), a workgroup (the compute) and a daily usage limit so an idle dev
# environment cannot run up a bill.
#
# The admin password is generated and kept in Secrets Manager by Redshift itself, so it
# never appears in Terraform state. The loader uses the Redshift Data API with IAM, not
# the password.

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  lake_arn   = "arn:${local.partition}:s3:::${var.lake_bucket}"
}

resource "aws_redshiftserverless_namespace" "this" {
  namespace_name        = "${var.name_prefix}-warehouse"
  db_name               = var.database_name
  admin_username        = "admin"
  manage_admin_password = true

  iam_roles            = [aws_iam_role.copy.arn]
  default_iam_role_arn = aws_iam_role.copy.arn

  log_exports = ["userlog", "connectionlog", "useractivitylog"]

  tags = var.tags
}

resource "aws_redshiftserverless_workgroup" "this" {
  namespace_name = aws_redshiftserverless_namespace.this.namespace_name
  workgroup_name = "${var.name_prefix}-warehouse"
  base_capacity  = var.base_capacity_rpu

  publicly_accessible  = false
  enhanced_vpc_routing = true
  subnet_ids           = length(var.subnet_ids) > 0 ? var.subnet_ids : null
  security_group_ids   = length(var.security_group_ids) > 0 ? var.security_group_ids : null

  tags = var.tags
}

resource "aws_redshiftserverless_usage_limit" "daily" {
  count = var.max_rpu_hours_per_day == null ? 0 : 1

  resource_arn  = aws_redshiftserverless_workgroup.this.arn
  usage_type    = "serverless-compute"
  period        = "daily"
  amount        = var.max_rpu_hours_per_day
  breach_action = "deactivate"
}
