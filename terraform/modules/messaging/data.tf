data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  backend_path = "${path.module}/../../../backend"
  build_path   = "${path.module}/../../../backend/.lambda_build"
}

# ─── Lambda Build ──────────────────────────────────────────────────────────────

resource "null_resource" "notify_build" {
  triggers = {
    requirements = filemd5("${local.backend_path}/requirements.lambda.txt")
    app_hash     = sha256(join("", [for f in fileset("${local.backend_path}/app", "**/*.py") : filemd5("${local.backend_path}/app/${f}")]))
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = <<-EOT
      set -e
      OUT="${local.build_path}/notify"
      rm -rf "$OUT"
      mkdir -p "$OUT"
      pip install -r "${local.backend_path}/requirements.lambda.txt" -t "$OUT" --quiet
      cp -r "${local.backend_path}/app" "$OUT/app"
      find "$OUT/app" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
      find "$OUT/app" -name "*.pyc" -delete 2>/dev/null || true
      cp "${local.backend_path}/app/lambdas/notify.py" "$OUT/notify.py"
    EOT
  }
}

resource "null_resource" "ingest_build" {
  triggers = {
    requirements = filemd5("${local.backend_path}/requirements.lambda.txt")
    app_hash     = sha256(join("", [for f in fileset("${local.backend_path}/app", "**/*.py") : filemd5("${local.backend_path}/app/${f}")]))
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = <<-EOT
      set -e
      OUT="${local.build_path}/ingest"
      rm -rf "$OUT"
      mkdir -p "$OUT"
      pip install -r "${local.backend_path}/requirements.lambda.txt" -t "$OUT" --quiet
      cp -r "${local.backend_path}/app" "$OUT/app"
      find "$OUT/app" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
      find "$OUT/app" -name "*.pyc" -delete 2>/dev/null || true
      cp "${local.backend_path}/app/lambdas/ingest.py" "$OUT/ingest.py"
    EOT
  }
}

# ─── Lambda Packaging ──────────────────────────────────────────────────────────
# archive_file data sources are evaluated at plan time — the build directories
# must exist before running terraform plan/apply. Run scripts/build_lambdas.sh first.

data "archive_file" "notify" {
  type        = "zip"
  source_dir  = "${local.build_path}/notify"
  output_path = "${local.build_path}/notify.zip"

  lifecycle {
    precondition {
      condition     = fileexists("${local.build_path}/notify/notify.py")
      error_message = "Lambda build directory missing. Run: bash scripts/build_lambdas.sh"
    }
  }
}

data "archive_file" "ingest" {
  type        = "zip"
  source_dir  = "${local.build_path}/ingest"
  output_path = "${local.build_path}/ingest.zip"

  lifecycle {
    precondition {
      condition     = fileexists("${local.build_path}/ingest/ingest.py")
      error_message = "Lambda build directory missing. Run: bash scripts/build_lambdas.sh"
    }
  }
}
