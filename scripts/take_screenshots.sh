#!/usr/bin/env bash
# Regenerate the README screenshots in docs/screenshots/ (1440x900).
#
# Prerequisites: a freshly seeded stack (make fresh), the frontend dev server (make frontend),
# and the finflow-n8n container running (see README). The script uploads the demo invoices,
# approves one with n8n briefly stopped, and uploads the demo bank statement.
set -euo pipefail

cd "$(dirname "$0")/../e2e"
mkdir -p ../docs/screenshots
npm install --no-audit --no-fund
npx playwright install chromium
npx playwright test --config=playwright.screenshots.config.ts "$@"
