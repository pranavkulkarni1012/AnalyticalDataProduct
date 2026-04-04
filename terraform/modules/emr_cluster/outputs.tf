# ──────────────────────────────────────────────────────────────────────────────
# EMR Cluster Module - Outputs
# ──────────────────────────────────────────────────────────────────────────────

output "application_id" {
  description = "EMR Serverless application ID"
  value       = var.mode == "serverless" ? aws_emrserverless_application.serverless[0].id : null
}

output "cluster_id" {
  description = "EMR EC2 cluster ID"
  value       = var.mode == "ec2" ? aws_emr_cluster.ec2[0].id : null
}

output "master_public_dns" {
  description = "Public DNS of the master node (EC2 mode only)"
  value       = var.mode == "ec2" ? aws_emr_cluster.ec2[0].master_public_dns : null
}
