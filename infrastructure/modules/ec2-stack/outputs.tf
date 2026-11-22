output "instance_id" {
  value = aws_instance.main.id
}

output "public_ip" {
  value = aws_instance.main.public_ip
}

output "public_dns" {
  value = aws_instance.main.public_dns
}

output "security_group_id" {
  value = aws_security_group.public.id
}
