#!/usr/bin/env bash
# FinFlow end-to-end smoke test (API must be running).
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000}"
API_V1="${API_BASE}/api/v1"

echo "=== FinFlow E2E Smoke Test ==="

TOKEN=$(curl -sf -X POST "${API_V1}/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=controller@acmecorp.com&password=Test1234!" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "✓ Login OK"

HEALTH=$(curl -sf "${API_BASE}/health")
echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status'] in ('healthy','degraded'); print('✓ Health:', d['status'])"

INVOICES=$(curl -sf "${API_V1}/invoices/?page_size=1" -H "Authorization: Bearer $TOKEN")
echo "$INVOICES" | python3 -c "import sys,json; d=json.load(sys.stdin); print('✓ Invoices API:', d.get('total', len(d.get('items',[]))), 'total')"

echo ""
echo "Smoke test passed."
