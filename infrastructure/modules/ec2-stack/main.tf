data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023*-x86_64"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

resource "aws_security_group" "public" {
  name_prefix = "${var.environment}-observability-"
  description = "Public access to the observability demonstration"
  vpc_id      = var.vpc_id

  dynamic "ingress" {
    for_each = var.ssh_allowed_cidr != "" ? [var.ssh_allowed_cidr] : []
    content {
      description = "SSH"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  dynamic "ingress" {
    for_each = var.public_access_cidr != "" ? [var.public_access_cidr] : []
    content {
      description = "Applications"
      from_port   = 8080
      to_port     = 8081
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  dynamic "ingress" {
    for_each = var.public_access_cidr != "" ? [var.public_access_cidr] : []
    content {
      description = "Grafana"
      from_port   = 3000
      to_port     = 3000
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  dynamic "ingress" {
    for_each = var.public_access_cidr != "" ? [var.public_access_cidr] : []
    content {
      description = "Prometheus and Alertmanager"
      from_port   = 9090
      to_port     = 9093
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "main" {
  ami                         = data.aws_ami.amazon_linux.id
  instance_type               = var.instance_type
  subnet_id                   = var.public_subnet_ids[0]
  associate_public_ip_address = true
  vpc_security_group_ids      = [aws_security_group.public.id]
  key_name                    = var.ssh_key_name != "" ? var.ssh_key_name : null

  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    delete_on_termination = true
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  user_data_base64 = base64encode(templatefile("${path.module}/user-data.sh", {
    git_repo_url        = var.git_repo_url
    project_archive_b64 = var.project_archive_b64
  }))

  tags = {
    Name = "${var.environment}-observability"
  }
}
