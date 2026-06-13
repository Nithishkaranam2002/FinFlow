#!/usr/bin/env bash
# Test route-approval + reject flow for GH-0099-A and verify INV-2026-0501 status.
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000/api/v1}"
INV_2026_0501_ID="85a8f0b1-a1b8-46e2-9b85-5a17966b8eec"
GH_0099_A_ID="db7df6bf-311d-4fb6-9c42-28ecbfd71db5"

print_error_response() {
  local label="$1"
  local http_status="$2"
  local body="$3"
  echo ""
  echo "ERROR: ${label}"
  echo "HTTP status: ${http_status}"
  echo "Response body:"
  echo "${body}"
  echo ""
}

http_get_invoice() {
  local invoice_id="$1"
  curl -sf -X GET "${API_BASE}/invoices/${invoice_id}" \
    -H "Authorization: Bearer ${TOKEN}"
}

echo "=== Step 1: Login as controller@acmecorp.com ==="
LOGIN_RESPONSE=$(curl -sf -X POST "${API_BASE}/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=controller@acmecorp.com&password=Test1234!") || {
  echo "Login request failed (curl exit $?)"
  exit 1
}
TOKEN=$(echo "${LOGIN_RESPONSE}" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "Login successful. Token saved."

echo ""
echo "=== Step 2: Check current status of INV-2026-0501 ==="
INV_0501=$(http_get_invoice "${INV_2026_0501_ID}")
INV_0501_STATUS=$(echo "${INV_0501}" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
echo "INV-2026-0501 (${INV_2026_0501_ID}) status: ${INV_0501_STATUS}"

echo ""
echo "=== Step 3: Check current status of GH-0099-A ==="
GH_INVOICE=$(http_get_invoice "${GH_0099_A_ID}")
GH_STATUS=$(echo "${GH_INVOICE}" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
echo "GH-0099-A (${GH_0099_A_ID}) current status: ${GH_STATUS}"

ROUTE_ALLOWED="matched review_required received"
PENDING_APPROVAL="pending_approval"
if echo "${ROUTE_ALLOWED}" | grep -qw "${GH_STATUS}"; then
  echo ""
  echo "=== Step 4: Route GH-0099-A through approval policy (POST /route-approval) ==="
  ROUTE_HTTP=$(curl -s -w "\n%{http_code}" -X POST "${API_BASE}/invoices/${GH_0099_A_ID}/route-approval" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json")
  ROUTE_BODY=$(echo "${ROUTE_HTTP}" | sed '$d')
  ROUTE_STATUS=$(echo "${ROUTE_HTTP}" | tail -n 1)
  if [[ "${ROUTE_STATUS}" -ge 200 && "${ROUTE_STATUS}" -lt 300 ]]; then
    ROUTED_STATUS=$(echo "${ROUTE_BODY}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))")
    ROUTED_ROLE=$(echo "${ROUTE_BODY}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('required_role','none'))")
    echo "Route-approval succeeded. Status: ${ROUTED_STATUS}, required_role: ${ROUTED_ROLE}"
  else
    print_error_response "route-approval for GH-0099-A" "${ROUTE_STATUS}" "${ROUTE_BODY}"
    exit 1
  fi
else
  echo ""
  if [[ "${GH_STATUS}" == "${PENDING_APPROVAL}" ]]; then
    echo "=== Step 4: Skipping route-approval (already pending_approval) ==="
  else
    echo "=== Step 4: Skipping route-approval (status '${GH_STATUS}' is not in: ${ROUTE_ALLOWED}) ==="
  fi
fi

echo ""
echo "=== Step 5: Reject GH-0099-A (PATCH /reject) ==="
REJECT_HTTP=$(curl -s -w "\n%{http_code}" -X PATCH "${API_BASE}/invoices/${GH_0099_A_ID}/reject" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Line item pricing unclear, needs vendor clarification"}')
REJECT_BODY=$(echo "${REJECT_HTTP}" | sed '$d')
REJECT_STATUS=$(echo "${REJECT_HTTP}" | tail -n 1)
if [[ "${REJECT_STATUS}" -ge 200 && "${REJECT_STATUS}" -lt 300 ]]; then
  echo "Reject succeeded."
else
  print_error_response "reject for GH-0099-A" "${REJECT_STATUS}" "${REJECT_BODY}"
  exit 1
fi

echo ""
echo "=== Step 6: Final status of GH-0099-A ==="
GH_FINAL=$(http_get_invoice "${GH_0099_A_ID}")
GH_FINAL_STATUS=$(echo "${GH_FINAL}" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
echo "GH-0099-A final status: ${GH_FINAL_STATUS}"
echo ""
echo "Done."
