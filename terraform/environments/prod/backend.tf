terraform {
  required_version = ">= 1.11"
  backend "s3" {
    bucket       = "cognis-terraform-state"
    key          = "prod/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true
    encrypt      = true
    assume_role = {
      role_arn = "arn:aws:iam::588106420806:role/cognis-terraform-role"
    }
  }
}
