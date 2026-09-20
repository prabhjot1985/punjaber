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

  # Both attachment resources below identify the instance by NAME, and the
  # name is a constant ("punjaber"). So when the instance is replaced, nothing
  # about these resources changes and Terraform leaves them alone -- while AWS
  # has silently dropped the real attachment along with the old instance. The
  # result is a running instance with neither its static IP nor its data disk,
  # which is exactly what happened here.
  #
  # replace_triggered_by ties them to the instance's identity rather than its
  # name, so a replacement re-attaches both.
  lifecycle {
    replace_triggered_by = [aws_lightsail_instance.this]
  }
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

  # The requested path, not the one the guest will see. On the NVMe-backed
  # blueprints this bundle uses, the kernel names it /dev/nvme1n1 and
  # /dev/xvdf never appears -- so user_data discovers the device instead of
  # trusting this value.
  disk_path = "/dev/xvdf"

  # See the note on the static IP attachment above: without this, replacing
  # the instance leaves the disk detached and the app silently loses its
  # persistent storage.
  lifecycle {
    replace_triggered_by = [aws_lightsail_instance.this]
  }
}

# --- No registry credentials, and no IAM user to fetch them.
#
# valkvlabs/punjaber is a public Docker Hub repository, so the instance pulls
# it anonymously. That removes what used to be the whole credential chain here:
# two SSM SecureString parameters, an IAM user, a long-lived access key baked
# into user_data, and a policy to read them back. It also removes the only
# manual step the deployment used to have.
#
# Pushing still needs a token, but that happens in GitHub Actions, not here
# (see .github/workflows/docker-publish.yml). Pull and push are different
# operations: a public repo is world-readable and still write-protected.
#
# If the image is ever made private, this is what has to come back: an
# aws_ssm_parameter pair holding the username and a read-only token (with
# lifecycle { ignore_changes = [value] } so Terraform never owns the secret),
# an aws_iam_user + access key scoped to ssm:GetParameter and kms:Decrypt on
# those two ARNs, the key passed into user_data, and a `docker login` before
# the pull. valkv-labs/valkvtrader/terraform/main.tf has that arrangement
# intact if it is needed as a reference.
