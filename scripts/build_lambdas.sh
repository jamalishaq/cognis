#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../backend" && pwd)"
BUILD_DIR="$BACKEND_DIR/.lambda_build"

build_lambda() {
  local name="$1"
  local handler_src="$BACKEND_DIR/app/lambdas/${name}.py"
  local out="$BUILD_DIR/$name"

  echo "Building Lambda: $name"
  rm -rf "$out"
  mkdir -p "$out"
  pip install -r "$BACKEND_DIR/requirements.lambda.txt" -t "$out" --quiet
  cp -r "$BACKEND_DIR/app" "$out/app"
  find "$out/app" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
  find "$out/app" -name "*.pyc" -delete 2>/dev/null || true
  cp "$handler_src" "$out/${name}.py"
  echo "  -> $out"
}

build_lambda notify
build_lambda ingest

echo "Lambda builds complete."
