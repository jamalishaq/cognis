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

data "archive_file" "notify" {
  depends_on  = [null_resource.notify_build]
  type        = "zip"
  source_dir  = "${local.build_path}/notify"
  output_path = "${local.build_path}/notify.zip"
}

data "archive_file" "ingest" {
  depends_on  = [null_resource.ingest_build]
  type        = "zip"
  source_dir  = "${local.build_path}/ingest"
  output_path = "${local.build_path}/ingest.zip"
}
