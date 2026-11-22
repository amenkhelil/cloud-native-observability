terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "cloud-native-observability"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

module "networking" {
  source = "../../modules/networking"

  environment         = var.environment
  vpc_cidr            = "10.20.0.0/16"
  availability_zones  = var.availability_zones
  public_subnet_cidrs = ["10.20.101.0/24", "10.20.102.0/24"]
}

module "ec2" {
  source = "../../modules/ec2-stack"

  environment        = var.environment
  aws_region         = var.aws_region
  vpc_id             = module.networking.vpc_id
  public_subnet_ids  = module.networking.public_subnet_ids
  git_repo_url       = var.git_repo_url
  instance_type      = var.instance_type
  ssh_key_name       = var.ssh_key_name
  ssh_allowed_cidr   = var.ssh_allowed_cidr
  public_access_cidr = var.public_access_cidr
}

resource "aws_cloudwatch_metric_alarm" "ec2_auto_recovery" {
  count               = var.enable_cloudwatch_alarm ? 1 : 0
  alarm_name          = "${var.environment}-ec2-auto-recovery"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  metric_name         = "StatusCheckFailed_System"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Maximum"
  threshold           = 1
  alarm_description   = "Auto-reboot EC2 instance upon hypervisor or OS status check failure"
  alarm_actions       = ["arn:aws:automate:${var.aws_region}:ec2:reboot"]

  dimensions = {
    InstanceId = module.ec2.instance_id
  }
}

resource "aws_cloudwatch_metric_alarm" "ec2_cpu" {
  count               = var.enable_cloudwatch_alarm ? 1 : 0
  alarm_name          = "${var.environment}-ec2-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Average"
  threshold           = 70
  alarm_description   = "EC2 CPU utilization exceeds 70%"

  dimensions = {
    InstanceId = module.ec2.instance_id
  }
}

output "public_ip" {
  value = module.ec2.public_ip
}

output "public_dns" {
  value = module.ec2.public_dns
}
