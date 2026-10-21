# One VM that runs docker/docker-compose.prod.yml (API, Postgres, Redis, Caddy HTTPS,
# Prometheus, Grafana). Same images as the Kubernetes path, at a fraction of the cost.

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Latest Ubuntu 24.04 LTS published by Canonical.
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
}

resource "aws_security_group" "aegis" {
  name        = "aegis-${var.environment}"
  description = "Aegis VM: HTTPS for everyone, SSH only from the admin CIDR"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH (admin only)"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }

  ingress {
    description = "HTTP (Caddy redirects to HTTPS and answers ACME challenges)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Outbound - image pulls, Lets Encrypt, OS updates"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_key_pair" "admin" {
  key_name   = "aegis-${var.environment}-admin"
  public_key = var.ssh_public_key
}

resource "aws_instance" "aegis" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.aegis.id]
  key_name               = aws_key_pair.admin.key_name
  user_data              = file("${path.module}/user_data.sh")

  # IMDSv2 only: blocks the SSRF-to-instance-credentials attack path.
  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
  }

  root_block_device {
    volume_size = var.root_volume_gb
    volume_type = "gp3"
    encrypted   = true
  }

  tags = {
    Name = "aegis-${var.environment}"
  }

  lifecycle {
    # A new Ubuntu AMI must not silently replace the running server (and its data).
    ignore_changes = [ami, user_data]
  }
}

# Static public IP: survives stop/start, so the DNS A record never changes.
resource "aws_eip" "aegis" {
  instance = aws_instance.aegis.id
  domain   = "vpc"
}
