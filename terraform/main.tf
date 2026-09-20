# --- Firewall: only 443 (tcp+udp, for HTTP/3) reachable from the internet.
# Port 22 is added only if var.open_ssh is explicitly flipped on.
resource "aws_lightsail_instance_public_ports" "this" {
  instance_name = aws_lightsail_instance.this.name

  port_info {
    protocol   = "tcp"
    from_port  = 443
    to_port    = 443
    cidrs      = ["0.0.0.0/0"]
    ipv6_cidrs = ["::/0"]
  }

  port_info {
    protocol   = "udp"
    from_port  = 443
    to_port    = 443
    cidrs      = ["0.0.0.0/0"]
    ipv6_cidrs = ["::/0"]
  }

  # Caddy needs port 80 reachable to answer the ACME HTTP-01 challenge and to
  # redirect http:// visitors to https://. Without it the first certificate
  # issuance fails and the site never comes up.
  port_info {
    protocol   = "tcp"
    from_port  = 80
    to_port    = 80
    cidrs      = ["0.0.0.0/0"]
    ipv6_cidrs = ["::/0"]
  }

  dynamic "port_info" {
    for_each = var.open_ssh ? [1] : []
    content {
      protocol   = "tcp"
      from_port  = 22
      to_port    = 22
      cidrs      = ["0.0.0.0/0"]
      ipv6_cidrs = ["::/0"]
    }
  }
}

# --- SSH keypair, only actually useful when open_ssh = true, but cheap to
# always create so it's ready if you need to flip open_ssh on for debugging.
resource "tls_private_key" "ssh" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_lightsail_key_pair" "this" {
  name       = "${var.instance_name}-key"
  public_key = tls_private_key.ssh.public_key_openssh
}

# --- The instance itself. dualstack gives it a public IPv6 address in
# addition to IPv4 (the static IPv4 is attached separately below).
resource "aws_lightsail_instance" "this" {
  name              = var.instance_name
  availability_zone = var.availability_zone
  blueprint_id      = var.blueprint_id
  bundle_id         = var.bundle_id
  key_pair_name     = aws_lightsail_key_pair.this.name
  ip_address_type   = "dualstack"

  user_data = templatefile("${path.module}/templates/user_data.sh.tftpl", {
    aws_region                  = var.aws_region
    bootstrap_access_key_id     = aws_iam_access_key.bootstrap.id
    bootstrap_secret_access_key = aws_iam_access_key.bootstrap.secret
    ssm_dockerhub_user_param    = aws_ssm_parameter.dockerhub_username.name
    ssm_dockerhub_pass_param    = aws_ssm_parameter.dockerhub_password.name
    docker_compose_content = templatefile("${path.module}/templates/docker-compose.prod.yml.tftpl", {
      dockerhub_namespace = var.dockerhub_namespace
      image_tag           = var.image_tag
      enable_studio       = var.enable_studio ? "1" : "0"
    })
    caddyfile_content = templatefile("${path.module}/templates/Caddyfile.tftpl", {
      domain_name = var.domain_name
    })
  })
}

# --- Static IPv4 so the domain's A record doesn't need to change if the
# instance is ever stopped/started (Lightsail rotates ephemeral IPs on stop).
resource "aws_lightsail_static_ip" "this" {
  name = "${var.instance_name}-ip"
}

resource "aws_lightsail_static_ip_attachment" "this" {
  static_ip_name = aws_lightsail_static_ip.this.name
  instance_name  = aws_lightsail_instance.this.name
}

# --- Persistent disk for /data: the SQLite progress database, the recordings,
# and the espeak-ng cache. This resource (and the data on it) survives
# deleting/recreating the instance, as long as the disk itself isn't destroyed.
#
# The recordings also exist in the published image and in git, so the disk is
# not the only copy — but a learner's progress lives nowhere else.
resource "aws_lightsail_disk" "data" {
  name              = "${var.instance_name}-data"
  size_in_gb        = var.disk_size_gb
  availability_zone = var.availability_zone
}

resource "aws_lightsail_disk_attachment" "data" {
  disk_name     = aws_lightsail_disk.data.name
  instance_name = aws_lightsail_instance.this.name
  disk_path     = "/dev/xvdf"
}

# --- SSM parameters for the Docker Hub pull credentials. Terraform creates
# the parameter (so the name/structure exists and can be referenced), but
# never manages the real value — `ignore_changes = [value]` means once you set
# the real value by hand (see outputs.next_steps), `terraform apply` will never
# overwrite it. This is the one manual step in the whole deployment, by design,
# and it keeps the token out of Terraform state and out of any .tf file.
resource "aws_ssm_parameter" "dockerhub_username" {
  name  = "/${var.instance_name}/dockerhub/username"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "dockerhub_password" {
  name  = "/${var.instance_name}/dockerhub/password"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

# --- Bootstrap IAM user: a narrowly-scoped credential baked into user_data so
# the instance can read the two SSM parameters above on first boot. A dedicated
# IAM user + access key rather than an instance role because Lightsail has no
# IAM-instance-role equivalent — it only supports its own service-linked role,
# not one you attach for your own app's permissions.
#
# Punjaber needs no other AWS permissions at runtime: it talks to nothing but
# its own disk.
resource "aws_iam_user" "bootstrap" {
  name = "${var.instance_name}-bootstrap"
}

resource "aws_iam_access_key" "bootstrap" {
  user = aws_iam_user.bootstrap.name
}

resource "aws_iam_user_policy" "bootstrap" {
  name = "${var.instance_name}-bootstrap-ssm-read"
  user = aws_iam_user.bootstrap.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadPunjaberParams"
        Effect = "Allow"
        Action = ["ssm:GetParameter"]
        Resource = [
          aws_ssm_parameter.dockerhub_username.arn,
          aws_ssm_parameter.dockerhub_password.arn,
        ]
      },
      {
        # SecureString parameters are encrypted with the account's default SSM
        # KMS key (alias/aws/ssm). Scoped to "*" rather than a specific key
        # ARN/alias because IAM resource-matching for KMS aliases vs. key ARNs
        # in this context isn't something to guess at — the same tradeoff
        # valkvtrader documents.
        Sid      = "DecryptWithDefaultSSMKey"
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = ["*"]
      },
    ]
  })
}
