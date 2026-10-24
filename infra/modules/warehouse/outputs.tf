output "namespace_name" {
  value = aws_redshiftserverless_namespace.this.namespace_name
}

output "workgroup_name" {
  description = "Pass to the loader (and the Redshift Data API) as the workgroup."
  value       = aws_redshiftserverless_workgroup.this.workgroup_name
}

output "workgroup_arn" {
  description = "Scope for IAM policies that submit statements through the Data API."
  value       = aws_redshiftserverless_workgroup.this.arn
}

output "database_name" {
  value = var.database_name
}

output "copy_role_arn" {
  description = "IAM role COPY runs as. It is also the namespace's default role."
  value       = aws_iam_role.copy.arn
}

output "admin_secret_arn" {
  description = "Secrets Manager secret Redshift created for the admin password."
  value       = aws_redshiftserverless_namespace.this.admin_password_secret_arn
}
