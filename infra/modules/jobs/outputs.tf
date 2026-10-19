output "job_names" {
  description = "Glue job name by stage: clean, model, quality."
  value       = { for stage, job in aws_glue_job.stage : stage => job.name }
}

output "role_arns" {
  description = "IAM role ARN by stage, for granting extra access from outside the module."
  value       = { for stage, role in aws_iam_role.stage : stage => role.arn }
}

output "entry_script_uri" {
  value = "s3://${var.artifacts_bucket}/${aws_s3_object.entry_script.key}"
}
