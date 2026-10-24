output "state_machine_arn" {
  description = "Start a run with aws stepfunctions start-execution --state-machine-arn <this>."
  value       = aws_sfn_state_machine.pipeline.arn
}

output "state_machine_name" {
  value = aws_sfn_state_machine.pipeline.name
}

output "stages" {
  description = "Glue jobs in the order the state machine runs them."
  value       = local.stages
}

output "schedule_name" {
  value = aws_scheduler_schedule.monthly.name
}
