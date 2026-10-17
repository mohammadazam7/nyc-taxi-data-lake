output "database_names" {
  description = "Glue database per zone: raw, clean, warehouse."
  value       = { for zone, db in aws_glue_catalog_database.this : zone => db.name }
}

output "crawler_names" {
  description = "Every crawler, in the order a pipeline run should start them."
  value = concat(
    [aws_glue_crawler.raw.name, aws_glue_crawler.clean.name],
    [for c in aws_glue_crawler.warehouse : c.name],
  )
}

output "crawler_role_arn" {
  value = aws_iam_role.crawler.arn
}

output "athena_workgroup" {
  value = aws_athena_workgroup.this.name
}
