output "app_name" {
  value = juju_application.kubeflow_volumes.name
}

output "provides" {
  value = {
  }
}

output "requires" {
  value = {
    ingress         = "ingress"
	dashboard_links = "dashboard-links"
	logging         = "logging"
  }
}
