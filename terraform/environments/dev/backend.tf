terraform {
  required_version = ">= 1.11"
  backend "s3" {
    bucket       = "cognis-terraform-state"
    key          = "dev/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true
    encrypt      = true
  }
}
