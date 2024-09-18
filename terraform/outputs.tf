output "app_name" {
  value = juju_application.kubeflow_volumes.name
}

output "provides" {
  value = {
    grpc = "grpc",
  }
}

output "requires" {
  value = {
    ingress = "ingress"
  }
}
