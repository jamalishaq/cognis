# observability/ — Resources to Provision

## CloudWatch Log Groups

- `aws_cloudwatch_log_group` fastapi — name `/cognis/${var.environment}/fastapi`
  - retention_in_days: dev=7, prod=30
- `aws_cloudwatch_log_group` notify_lambda — name `/cognis/${var.environment}/lambda/notify`
  - retention_in_days: dev=7, prod=30
- `aws_cloudwatch_log_group` ingest_lambda — name `/cognis/${var.environment}/lambda/ingest`
  - retention_in_days: dev=7, prod=30

## CloudWatch Alarms

### Endpoint Latency
- `aws_cloudwatch_metric_alarm` analyse_p95_latency — metric `TargetResponseTime` on ALB, p95 > 15s for 2 consecutive periods
- `aws_cloudwatch_metric_alarm` chat_p95_latency — metric `TargetResponseTime` on ALB, p95 > 16s for 2 consecutive periods

### Error Rates
- `aws_cloudwatch_metric_alarm` ecs_5xx_errors — metric `HTTPCode_Target_5XX_Count` on ALB target group, > 5 errors in 5 minutes
- `aws_cloudwatch_metric_alarm` ecs_task_restarts — metric `RunningTaskCount` on ECS service drops below desired count

### Bedrock Throttling
- `aws_cloudwatch_metric_alarm` bedrock_throttles — metric `InvocationThrottles` on Bedrock, > 0 for 2 consecutive periods

### SQS Queue Depth
- `aws_cloudwatch_metric_alarm` notification_queue_depth — metric `ApproximateNumberOfMessagesVisible` on notification queue, > 10 for 5 minutes
- `aws_cloudwatch_metric_alarm` ingestion_queue_depth — metric `ApproximateNumberOfMessagesVisible` on ingestion queue, > 10 for 5 minutes

### Lambda Errors
- `aws_cloudwatch_metric_alarm` notify_lambda_errors — metric `Errors` on notify Lambda, > 0 for 2 consecutive periods
- `aws_cloudwatch_metric_alarm` ingest_lambda_errors — metric `Errors` on ingest Lambda, > 0 for 2 consecutive periods

All alarms: `actions_enabled = true` in prod, `actions_enabled = false` in dev

## CloudWatch Dashboard
- `aws_cloudwatch_dashboard` — name `cognis-${var.environment}`
- Widgets: ALB request count, ALB 5xx rate, ECS CPU/memory, Bedrock invocations, SQS queue depths, Lambda errors

## AWS X-Ray
- `aws_xray_sampling_rule` — name `cognis-${var.environment}`
  - `fixed_rate = 1.0` in dev (sample all requests)
  - `fixed_rate = 0.1` in prod (sample 10%)
  - `resource_arn = "*"`, `service_name = "cognis"`, `service_type = "*"`, `host = "*"`, `http_method = "*"`, `url_path = "*"`, `version = 1`

## Custom Metric Alarms (Application)

These alarm on metrics emitted via EMF from the FastAPI application:

- `aws_cloudwatch_metric_alarm` pipeline_slo — `Cognis/Pipeline` `pipeline_duration_ms` p95 > 15000ms for 2 consecutive periods
- `aws_cloudwatch_metric_alarm` retrieval_degraded — `Cognis/Pipeline` `retrieval_degraded` sum > 10% of `incidents_processed` over 1hr
- `aws_cloudwatch_metric_alarm` judge_quality — `Cognis/Judge` `judge_groundedness` avg < 3 over 1hr
- `aws_cloudwatch_metric_alarm` judge_flags — `Cognis/Judge` `judge_flagged` rate > 20% over 1hr
- `aws_cloudwatch_metric_alarm` agent_tool_calls — `Cognis/Pipeline` `agent_tool_calls` avg > 5 over 1hr


- `aws_sns_topic` alarms — name `cognis-prod-alarms`
- `aws_sns_topic_subscription` — email endpoint for on-call engineer
- All CloudWatch alarms in prod have `alarm_actions = [sns_topic_arn]`

## Outputs
- `fastapi_log_group_name`
- `notify_lambda_log_group_name`
- `ingest_lambda_log_group_name`
- `dashboard_name`
