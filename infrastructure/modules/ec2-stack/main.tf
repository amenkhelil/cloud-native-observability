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
  description = "Hardened public access through Reverse Proxy Gateway"
  vpc_id      = var.vpc_id

  dynamic "ingress" {
    for_each = var.ssh_allowed_cidr != "" ? [var.ssh_allowed_cidr] : []
    content {
      description = "SSH Administrative Tunnel"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  dynamic "ingress" {
    for_each = var.public_access_cidr != "" ? [var.public_access_cidr] : []
    content {
      description = "HTTP Gateway Ingress"
      from_port   = 80
      to_port     = 80
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  dynamic "ingress" {
    for_each = var.public_access_cidr != "" ? [var.public_access_cidr] : []
    content {
      description = "HTTPS Gateway Ingress"
      from_port   = 443
      to_port     = 443
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
  user_data_replace_on_change = true

  tags = {
    Name = "${var.environment}-observability"
  }
}
