#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-nginx/ssl}"
mkdir -p "$OUT_DIR"

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout "$OUT_DIR/key.pem" \
  -out "$OUT_DIR/cert.pem" \
  -subj "/CN=localhost/O=FinFlow/C=US"

echo "Generated self-signed TLS cert in $OUT_DIR"
