output "public_ip" {
  description = "Point your domain's A record here"
  value       = aws_eip.aegis.public_ip
}

output "ssh_command" {
  description = "Log in to finish the deploy (create docker/.env, then docker compose up)"
  value       = "ssh ubuntu@${aws_eip.aegis.public_ip}"
}
