variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "availability_zones" {
  type    = list(string)
  default = ["us-east-1a", "us-east-1b"]
}

variable "instance_type" {
  type    = string
  default = "t3.small"
}

variable "ssh_key_name" {
  type    = string
  default = ""
}

variable "ssh_allowed_cidr" {
  type    = string
  default = ""
}

variable "public_access_cidr" {
  type        = string
  default     = "0.0.0.0/0"
  description = "CIDR allowed to access published application and observability ports."
}

variable "enable_cloudwatch_alarm" {
  type        = bool
  default     = true
  description = "Enable CloudWatch infrastructure alarms and automated EC2 recovery actions."
}

variable "git_repo_url" {
  type        = string
  default     = "https://github.com/amenkhelil/cloud-native-observability.git"
  description = "Git repository URL to clone on the EC2 instance (leave empty to use embedded zip)."
}
