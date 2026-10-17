output "lake_bucket" {
  description = "Bucket holding every zone of the lake."
  value       = aws_s3_bucket.this["lake"].id
}

output "lake_bucket_arn" {
  value = aws_s3_bucket.this["lake"].arn
}

output "lake_root" {
  description = "Value for NYC_LAKE_ROOT in AWS."
  value       = "s3://${aws_s3_bucket.this["lake"].id}"
}

output "artifacts_bucket" {
  description = "Bucket for Glue scripts, the package wheel and reference files."
  value       = aws_s3_bucket.this["artifacts"].id
}

output "artifacts_bucket_arn" {
  value = aws_s3_bucket.this["artifacts"].arn
}

output "athena_results_bucket" {
  value = aws_s3_bucket.this["athena"].id
}

output "athena_results_bucket_arn" {
  value = aws_s3_bucket.this["athena"].arn
}
