variable "environment" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "git_repo_url" {
  type        = string
  default     = ""
  description = "Public Git repository URL to clone on the EC2 instance."
}

variable "project_archive_b64" {
  type        = string
  default     = ""
  description = "Base64 encoded zip archive for fallback."
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
  type        = string
  default     = ""
  description = "Optional CIDR allowed for SSH. Leave empty to disable SSH."
}

variable "public_access_cidr" {
  type        = string
  default     = ""
  description = "CIDR allowed to access published application and observability ports."
}
