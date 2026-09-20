output "static_ip" {
  description = "Static IPv4 address. Point your domain's A record here."
  value       = aws_lightsail_static_ip.this.ip_address
}

output "ipv6_address" {
  description = "IPv6 address. Optionally point your domain's AAAA record here."
  value       = aws_lightsail_instance.this.ipv6_addresses[0]
}

output "instance_name" {
  description = "Lightsail instance name."
  value       = aws_lightsail_instance.this.name
}

output "app_url" {
  description = "Where the course will be served once DNS resolves and Caddy has a certificate."
  value       = "https://${var.domain_name}"
}

output "image" {
  description = "Docker Hub image this instance pulls."
  value       = "${var.dockerhub_namespace}/punjaber:${var.image_tag}"
}

output "ssh_private_key" {
  description = "Private key for aws_lightsail_key_pair.this. Only useful if open_ssh = true. Save with `terraform output -raw ssh_private_key > punjaber-key.pem && chmod 600 punjaber-key.pem`."
  value       = tls_private_key.ssh.private_key_pem
  sensitive   = true
}

output "next_steps" {
  description = "The manual steps Terraform intentionally leaves for you."
  value       = <<-EOT
    Deployment applied. There are no secrets to set: ${var.dockerhub_namespace}/punjaber
    is a public image and the instance pulls it anonymously. Two things remain.

    1. Point DNS at the instance, and let it propagate BEFORE step 2 —
       Caddy's first certificate request fails if the name does not yet
       resolve, and repeated failures hit Let's Encrypt rate limits:

      A    ${var.domain_name}  -> ${aws_lightsail_static_ip.this.ip_address}
      AAAA ${var.domain_name}  -> ${aws_lightsail_instance.this.ipv6_addresses[0]}   (optional)

    2. If the instance booted before DNS resolved, recreate it so user_data
       runs again. A reboot is NOT enough: cloud-init runs user_data only on
       an instance's first boot.

      terraform apply -replace=aws_lightsail_instance.this

    Then check it came up:

      curl -s https://${var.domain_name}/api/health

    Expect "studio": ${var.enable_studio}, and a recording count matching the
    published image. If it does not come up, SSH in (terraform apply
    -var open_ssh=true) and read /var/log/punjaber-bootstrap.log.

    Worth knowing about this deployment:

      - Publishing a new image: cut a GitHub Release. That triggers
        .github/workflows/docker-publish.yml, which pushes
        ${var.dockerhub_namespace}/punjaber:<tag> and :latest. To roll it out,
        SSH in and `cd /opt/punjaber && docker compose pull && docker compose up -d`.
      - Pushing needs a Docker Hub token; pulling does not. The token lives in
        GitHub Actions secrets, never on this instance.
      - The recording studio is ${var.enable_studio ? "ENABLED — anyone who can reach https://${var.domain_name} can overwrite your recordings. Only safe if that domain is genuinely private." : "disabled, which is the right default for a public domain. Record locally, publish a new image, and pull it."}
      - Progress is per-profile, keyed by the X-Punjaber-User header the
        browser sends. Anyone who guesses a profile name can read that
        profile's progress; there are no accounts.
      - The recordings and the SQLite database live on the attached disk
        (${aws_lightsail_disk.data.name}). Destroying the instance keeps them;
        destroying that disk does not.

    Verify before relying on this deployment (see terraform/README.md):
      - var.bundle_id is still a valid/current Lightsail bundle for ${var.aws_region}
      - the attached disk showed up as /dev/xvdf on this blueprint (check
        /var/log/punjaber-bootstrap.log if /data looks empty)
  EOT
}
