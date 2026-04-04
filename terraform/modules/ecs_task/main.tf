# ──────────────────────────────────────────────────────────────────────────────
# ECS Task Module
# Creates a Fargate task definition, ECS service, and CloudWatch log group.
# ──────────────────────────────────────────────────────────────────────────────

data "aws_region" "current" {}

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${var.task_family}"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

resource "aws_ecs_task_definition" "task" {
  family                   = var.task_family
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  task_role_arn            = var.task_role_arn
  execution_role_arn       = var.execution_role_arn

  container_definitions = jsonencode([
    {
      name      = var.task_family
      image     = var.container_image
      cpu       = var.cpu
      memory    = var.memory
      essential = true

      portMappings = var.container_port != null ? [
        {
          containerPort = var.container_port
          hostPort      = var.container_port
          protocol      = "tcp"
        }
      ] : []

      environment = [
        for k, v in var.environment_variables : {
          name  = k
          value = v
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])

  tags = var.tags
}

resource "aws_ecs_service" "service" {
  name            = var.task_family
  cluster         = var.cluster_arn
  task_definition = aws_ecs_task_definition.task.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.subnets
    security_groups  = var.security_groups
    assign_public_ip = false
  }

  tags = var.tags
}
