output "alert_topic_arn" {
  description = "Topic every alert publishes to. Pass it to the jobs module for data-quality breaches."
  value       = aws_sns_topic.alerts.arn
}

output "glue_failure_rule" {
  value = aws_cloudwatch_event_rule.glue_job_failed.name
}

output "alarm_names" {
  description = "CloudWatch alarm name by Glue job."
  value       = { for job, alarm in aws_cloudwatch_metric_alarm.glue_failed_tasks : job => alarm.alarm_name }
}
