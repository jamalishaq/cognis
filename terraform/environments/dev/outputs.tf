output "ecr_repository_url" {
  value = module.compute.ecr_repository_url
}

output "ecs_cluster_name" {
  value = module.compute.ecs_cluster_name
}

output "ecs_service_name" {
  value = module.compute.ecs_service_name
}

output "alb_arn" {
  value = module.networking.alb_arn
}

output "user_pool_id" {
  value = module.auth.user_pool_id
}

output "user_pool_client_id" {
  value = module.auth.user_pool_client_id
}

output "notification_queue_url" {
  value = module.messaging.notification_queue_url
}

output "ingestion_queue_url" {
  value = module.messaging.ingestion_queue_url
}

output "dashboard_name" {
  value = module.observability.dashboard_name
}
