locals {
  # Extract short IDs for CloudWatch dimensions from ARNs
  alb_suffix          = split("/", var.alb_arn)[2]
  alb_id              = "app/${local.alb_suffix}/${split("/", var.alb_arn)[3]}"
  target_group_id     = "targetgroup/${split("/", var.alb_target_group_arn)[1]}/${split("/", var.alb_target_group_arn)[2]}"
  alarm_actions       = var.enable_alarm_actions && var.oncall_email != "" ? [aws_sns_topic.alarms[0].arn] : []
}

# ─── CloudWatch Log Groups ─────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "fastapi" {
  name              = "/cognis/${var.environment}/fastapi"
  retention_in_days = var.log_retention_days

  tags = {
    Name        = "/cognis/${var.environment}/fastapi"
    Environment = var.environment
  }
}

resource "aws_cloudwatch_log_group" "notify_lambda" {
  name              = "/cognis/${var.environment}/lambda/notify"
  retention_in_days = var.log_retention_days

  tags = {
    Name        = "/cognis/${var.environment}/lambda/notify"
    Environment = var.environment
  }
}

resource "aws_cloudwatch_log_group" "ingest_lambda" {
  name              = "/cognis/${var.environment}/lambda/ingest"
  retention_in_days = var.log_retention_days

  tags = {
    Name        = "/cognis/${var.environment}/lambda/ingest"
    Environment = var.environment
  }
}

# ─── CloudWatch Alarms ─────────────────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "analyse_p95_latency" {
  alarm_name          = "cognis-${var.environment}-analyse-p95-latency"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "TargetResponseTime"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  extended_statistic  = "p95"
  threshold           = 15
  alarm_description   = "Analyse endpoint p95 latency > 15s"
  actions_enabled     = var.enable_alarm_actions
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    LoadBalancer = local.alb_id
  }

  tags = { Environment = var.environment }
}

resource "aws_cloudwatch_metric_alarm" "chat_p95_latency" {
  alarm_name          = "cognis-${var.environment}-chat-p95-latency"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "TargetResponseTime"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  extended_statistic  = "p95"
  threshold           = 16
  alarm_description   = "Chat endpoint p95 latency > 16s"
  actions_enabled     = var.enable_alarm_actions
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    LoadBalancer = local.alb_id
  }

  tags = { Environment = var.environment }
}

resource "aws_cloudwatch_metric_alarm" "ecs_5xx_errors" {
  alarm_name          = "cognis-${var.environment}-ecs-5xx-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "ECS target 5xx errors > 5 in 5 minutes"
  actions_enabled     = var.enable_alarm_actions
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    LoadBalancer = local.alb_id
    TargetGroup  = local.target_group_id
  }

  tags = { Environment = var.environment }
}

resource "aws_cloudwatch_metric_alarm" "ecs_task_restarts" {
  alarm_name          = "cognis-${var.environment}-ecs-task-restarts"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "RunningTaskCount"
  namespace           = "ECS/ContainerInsights"
  period              = 60
  statistic           = "Average"
  threshold           = 1
  alarm_description   = "ECS running task count dropped below desired"
  actions_enabled     = var.enable_alarm_actions
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_service_name
  }

  tags = { Environment = var.environment }
}

resource "aws_cloudwatch_metric_alarm" "bedrock_throttles" {
  alarm_name          = "cognis-${var.environment}-bedrock-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "InvocationThrottles"
  namespace           = "AWS/Bedrock"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Bedrock invocation throttles detected"
  actions_enabled     = var.enable_alarm_actions
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  tags = { Environment = var.environment }
}

resource "aws_cloudwatch_metric_alarm" "notification_queue_depth" {
  alarm_name          = "cognis-${var.environment}-notification-queue-depth"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Average"
  threshold           = 10
  alarm_description   = "Notification queue depth > 10 for 5 minutes"
  actions_enabled     = var.enable_alarm_actions
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    QueueName = var.notification_queue_name
  }

  tags = { Environment = var.environment }
}

resource "aws_cloudwatch_metric_alarm" "ingestion_queue_depth" {
  alarm_name          = "cognis-${var.environment}-ingestion-queue-depth"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Average"
  threshold           = 10
  alarm_description   = "Ingestion queue depth > 10 for 5 minutes"
  actions_enabled     = var.enable_alarm_actions
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    QueueName = var.ingestion_queue_name
  }

  tags = { Environment = var.environment }
}

resource "aws_cloudwatch_metric_alarm" "notify_lambda_errors" {
  alarm_name          = "cognis-${var.environment}-notify-lambda-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Notification Lambda errors detected"
  actions_enabled     = var.enable_alarm_actions
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    FunctionName = var.notify_lambda_function_name
  }

  tags = { Environment = var.environment }
}

resource "aws_cloudwatch_metric_alarm" "ingest_lambda_errors" {
  alarm_name          = "cognis-${var.environment}-ingest-lambda-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Ingestion Lambda errors detected"
  actions_enabled     = var.enable_alarm_actions
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    FunctionName = var.ingest_lambda_function_name
  }

  tags = { Environment = var.environment }
}

# ─── CloudWatch Dashboard ──────────────────────────────────────────────────────

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "cognis-${var.environment}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "ALB Request Count"
          metrics = [["AWS/ApplicationELB", "RequestCount", "LoadBalancer", local.alb_id]]
          period = 60
          stat   = "Sum"
          region = "us-east-1" # hardcoded — project is us-east-1 only
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "ALB 5xx Rate"
          metrics = [["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", local.alb_id, "TargetGroup", local.target_group_id]]
          period = 60
          stat   = "Sum"
          region = "us-east-1" # hardcoded — project is us-east-1 only
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "ECS CPU Utilisation"
          metrics = [["AWS/ECS", "CPUUtilization", "ClusterName", var.ecs_cluster_name, "ServiceName", var.ecs_service_name]]
          period = 60
          stat   = "Average"
          region = "us-east-1" # hardcoded — project is us-east-1 only
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "ECS Memory Utilisation"
          metrics = [["AWS/ECS", "MemoryUtilization", "ClusterName", var.ecs_cluster_name, "ServiceName", var.ecs_service_name]]
          period = 60
          stat   = "Average"
          region = "us-east-1" # hardcoded — project is us-east-1 only
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 12
        height = 6
        properties = {
          title  = "SQS Queue Depths"
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.notification_queue_name],
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.ingestion_queue_name]
          ]
          period = 60
          stat   = "Average"
          region = "us-east-1" # hardcoded — project is us-east-1 only
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 12
        width  = 12
        height = 6
        properties = {
          title  = "Lambda Errors"
          metrics = [
            ["AWS/Lambda", "Errors", "FunctionName", var.notify_lambda_function_name],
            ["AWS/Lambda", "Errors", "FunctionName", var.ingest_lambda_function_name]
          ]
          period = 60
          stat   = "Sum"
          region = "us-east-1" # hardcoded — project is us-east-1 only
        }
      }
    ]
  })
}

# ─── X-Ray ────────────────────────────────────────────────────────────────────

resource "aws_xray_sampling_rule" "main" {
  rule_name      = "cognis-${var.environment}"
  priority       = 1000
  resource_arn   = "*"
  service_name   = "cognis"
  service_type   = "*"
  host           = "*"
  http_method    = "*"
  url_path       = "*"
  fixed_rate     = var.xray_fixed_rate
  reservoir_size = 1
  version        = 1

  tags = { Environment = var.environment }
}

# ─── SNS Topic for Alarm Notifications (prod only) ────────────────────────────

resource "aws_sns_topic" "alarms" {
  count = var.enable_alarm_actions && var.oncall_email != "" ? 1 : 0
  name  = "cognis-prod-alarms"

  tags = {
    Name        = "cognis-prod-alarms"
    Environment = var.environment
  }
}

resource "aws_sns_topic_subscription" "oncall_email" {
  count     = var.enable_alarm_actions && var.oncall_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alarms[0].arn
  protocol  = "email"
  endpoint  = var.oncall_email
}
