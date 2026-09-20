variable "aws_region" {
  description = "AWS region for the Lightsail instance and disk."
  type        = string
  default     = "us-west-2"
}

variable "availability_zone" {
  description = "Availability zone within aws_region for the instance and disk (must match each other)."
  type        = string
  default     = "us-west-2a"
}

variable "domain_name" {
  description = <<-EOT
    Domain name you'll point at this instance (A record -> the static IPv4
    output, and optionally an AAAA record -> the IPv6 output). Required:
    Caddy needs it to issue a Let's Encrypt cert.

    HTTPS is not optional here even for a course that holds no secrets — the
    recording studio uses getUserMedia, which browsers only grant on a secure
    origin. Over plain HTTP the microphone is unavailable. No default on
    purpose.
  EOT
  type        = string
}

variable "instance_name" {
  description = "Lightsail instance name."
  type        = string
  default     = "punjaber"
}

variable "bundle_id" {
  description = <<-EOT
    Lightsail bundle (size/price tier). VERIFY BEFORE APPLYING — bundle IDs
    and pricing change over time and by generation:
      aws lightsail get-bundles --region <aws_region>

    "micro_3_0" was the ~$5/mo tier (1 GB RAM) as of writing. Punjaber is a
    single Python process serving static files and small JSON; the only
    CPU-heavy path is espeak-ng synthesis, which runs once per phrase and is
    then cached — and is bypassed entirely for any phrase that has a
    recording. 1 GB is comfortable.
  EOT
  type        = string
  default     = "micro_3_0"
}

variable "blueprint_id" {
  description = "Lightsail OS blueprint."
  type        = string
  default     = "ubuntu_22_04"
}

variable "disk_size_gb" {
  description = <<-EOT
    Size (GB) of the persistent disk holding the SQLite progress database,
    the recordings and the synthesis cache. Survives instance deletion as long
    as the disk resource itself isn't destroyed.

    The recordings are the large part at ~8.4 MB today, so this is enormous
    relative to the need. It matches valkvtrader rather than being sized to
    Punjaber, on the grounds that a consistent disk size across the estate is
    worth more than the few cents saved.
  EOT
  type        = number
  default     = 10
}

variable "dockerhub_namespace" {
  description = "Docker Hub namespace/account the punjaber image is published under."
  type        = string
  default     = "valkvlabs"
}

variable "image_tag" {
  description = "Tag of the valkvlabs/punjaber image to deploy (e.g. a release tag, or \"latest\")."
  type        = string
  default     = "latest"
}

variable "enable_studio" {
  description = <<-EOT
    Whether the deployed app accepts audio uploads.

    Defaults to false, and think before flipping it. Punjaber has no
    authentication: with the studio on, anyone who reaches the URL could
    overwrite or delete every recording in the course. Record locally with
    `make start`, cut a release, and redeploy — the recordings travel in the
    image and are seeded onto the disk on first boot.

    Turn it on only if the domain is genuinely private, or temporarily while
    you fix a take, then turn it back off.
  EOT
  type        = bool
  default     = false
}

variable "open_ssh" {
  description = <<-EOT
    If true, also opens port 22 (SSH) to the internet. Defaults to false —
    only 443 is exposed. Flip this on temporarily
    (terraform apply -var open_ssh=true) when you need to shell in for
    debugging, then flip it back off.
  EOT
  type        = bool
  default     = false
}
