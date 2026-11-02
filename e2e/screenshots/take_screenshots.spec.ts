/**
 * Captures the README screenshots into docs/screenshots/ (1440x900).
 *
 * Needs a freshly seeded stack (make fresh), the Vite dev server (make frontend), and the
 * finflow-n8n container with APPROVAL_WEBHOOK_URL set (see README). It creates its own data
 * through the UI: uploads the 4 demo invoices, approves one, and uploads the demo statement.
 * Run it with scripts/take_screenshots.sh.
 */
import { execSync } from 'node:child_process'
import path from 'node:path'
import { expect, test, type Browser, type Locator, type Page } from '@playwright/test'

const REPO = path.resolve(__dirname, '..', '..')
const SHOTS = path.join(REPO, 'docs', 'screenshots')
const DEMO = path.join(REPO, 'demo_invoices')
// Seeded synthetic test users (README "Test users"); override with DEMO_PASSWORD if changed.
const PASSWORD = process.env.DEMO_PASSWORD || 'Test1234!'
const N8N_CONTAINER = process.env.N8N_CONTAINER || 'finflow-n8n'

const DEMO_INVOICES = [
  { key: 'clean', file: 'a_clean_kestrel_ridge.pdf', vendor: 'Kestrel Ridge Electrical Supply' },
  { key: 'scanned', file: 'b_scanned_ambervolt.pdf', vendor: 'Ambervolt Wire & Conduit' },
  { key: 'threshold', file: 'c_threshold_northpine.pdf', vendor: 'Northpine Electric Distributors' },
  { key: 'large', file: 'd_large_halvorsen_teague.pdf', vendor: 'Halvorsen-Teague Lighting & Power' },
] as const

type InvoiceKey = (typeof DEMO_INVOICES)[number]['key']

// Any email or URL host outside the reserved .example / .test domains is masked in every
// screenshot, so seeded user addresses or a misread real-looking domain can never show up.
const UNSAFE_EMAIL = /[\w.+-]+@(?![\w.-]*\.(?:example|test)\b)[\w-]+(?:\.[\w-]+)+/i
const UNSAFE_URL = /https?:\/\/(?![^\s/]*\.(?:example|test)\b)[^\s/]+/i

const MASK_ATTRIBUTE = 'data-screenshot-mask'

/** Tag the element holding each unsafe text node. Matching per text node (not per container,
 * whose text runs fields together) keeps the masks tight. */
async function tagUnsafeContactText(page: Page) {
  await page.evaluate(
    ({ patterns, attribute }) => {
      const regexes = patterns.map((source) => new RegExp(source, 'i'))
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const text = node.textContent ?? ''
        if (regexes.some((regex) => regex.test(text))) node.parentElement?.setAttribute(attribute, '')
      }
    },
    { patterns: [UNSAFE_EMAIL.source, UNSAFE_URL.source], attribute: MASK_ATTRIBUTE },
  )
}

async function shot(page: Page, name: string, hide: Locator[] = []) {
  await page.waitForTimeout(800) // let charts and transitions settle
  await tagUnsafeContactText(page)
  await page.screenshot({
    path: path.join(SHOTS, `${name}.png`),
    mask: [page.locator(`[${MASK_ATTRIBUTE}]`), ...hide],
    maskColor: '#e2e8f0',
  })
}

/** The value line of an "Extracted Data" field card, located by its label. */
function extractedValue(page: Page, label: string): Locator {
  return page
    .getByText(label, { exact: true })
    .locator('xpath=ancestor::div[1]/following-sibling::*[1]')
}

async function signIn(browser: Browser, email: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage()
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL('/')
  return page
}

async function waitForInvoiceStatus(page: Page, id: string, statuses: string[]) {
  await expect
    .poll(
      async () => (await (await page.request.get(`/api/v1/invoices/${id}`)).json()).status,
      { timeout: 180_000, intervals: [3_000] },
    )
    .toMatch(new RegExp(`^(${statuses.join('|')})$`))
}

async function n8nHealthy(): Promise<boolean> {
  try {
    return (await fetch('http://localhost:5678/healthz')).ok
  } catch {
    return false
  }
}

test('README screenshots', async ({ browser }) => {
  // 1. Login page
  const anon = await (await browser.newContext()).newPage()
  await anon.goto('/login')
  await expect(anon.getByRole('heading', { name: 'Welcome to FinFlow' })).toBeVisible()
  // The dev login page prints the seeded credentials, and the email placeholder is a real
  // domain; keep both out of the screenshot.
  const devCredentials = anon.getByText('Local dev credentials').locator('..')
  await shot(anon, '01-login', [devCredentials, anon.getByLabel('Email')])

  // Upload the 4 demo invoices as the AP clerk, through the Invoices page.
  const clerk = await signIn(browser, 'clerk@acmecorp.com')
  await clerk.getByRole('link', { name: 'Invoices' }).click()
  await clerk.getByRole('button', { name: 'Upload Invoice' }).click()
  const vendorSelect = clerk.locator('select', {
    has: clerk.locator('option', { hasText: 'Select a vendor...' }),
  })
  await expect(vendorSelect).toBeVisible()
  const ids = {} as Record<InvoiceKey, string>
  for (const invoice of DEMO_INVOICES) {
    await vendorSelect.selectOption({ label: invoice.vendor })
    const uploaded = clerk.waitForResponse(
      (r) => r.url().includes('/invoices/upload') && r.request().method() === 'POST',
    )
    await clerk.locator('input[type="file"]').setInputFiles(path.join(DEMO, invoice.file))
    ids[invoice.key] = (await (await uploaded).json()).invoice_id
  }
  for (const key of Object.keys(ids) as InvoiceKey[]) {
    await waitForInvoiceStatus(clerk, ids[key], ['pending_approval', 'review_required'])
  }

  // 2. Dashboard (after today's uploads) and 3. invoice list
  await clerk.goto('/')
  await expect(clerk.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  await shot(clerk, '02-dashboard')
  await clerk.goto('/invoices')
  await expect(clerk.getByText('KRES-240518')).toBeVisible({ timeout: 30_000 })
  await shot(clerk, '03-invoice-list')

  // 4. Scanned invoice with the "Why this needs attention" box
  await clerk.goto(`/invoices/${ids.scanned}`)
  await expect(clerk.getByText('Why this needs attention')).toBeVisible()
  // Contact fields read from the noisy scan can come out as a real-looking domain.
  await shot(clerk, '04-scanned-invoice-attention', [
    extractedValue(clerk, 'Vendor Email'),
    extractedValue(clerk, 'Notes'),
  ])

  // 5. Just-under-limit invoice: fraud flag card in view
  await clerk.goto(`/invoices/${ids.threshold}`)
  await expect(clerk.getByText('Why this needs attention')).toBeVisible()
  await clerk.getByRole('heading', { name: 'Fraud Flags' }).scrollIntoViewIfNeeded()
  await clerk.evaluate(() => window.scrollBy(0, -260))
  await shot(clerk, '05-threshold-fraud-flag')

  // 6. Approver cannot approve the large invoice
  const approver = await signIn(browser, 'approver@acmecorp.com')
  await approver.goto(`/invoices/${ids.large}`)
  const blocked = approver.getByText(/Requires controller role or higher/)
  await blocked.scrollIntoViewIfNeeded()
  await expect(blocked).toBeVisible()
  await approver.evaluate(() => window.scrollBy(0, 200))
  await shot(approver, '06-approver-blocked')

  // 7-8. Integrations: approve with n8n stopped (red), then start n8n and Retry now (green)
  const controller = await signIn(browser, 'controller@acmecorp.com')
  execSync(`docker stop ${N8N_CONTAINER}`)
  try {
    await controller.goto(`/invoices/${ids.large}`)
    await controller.getByRole('button', { name: 'Approve', exact: true }).click()
    await waitForInvoiceStatus(controller, ids.large, ['approved'])
    await controller.goto('/integrations')
    await expect(controller.getByText('Last delivery failed')).toBeVisible({ timeout: 30_000 })
    await shot(controller, '07-integrations-failed')
    // Keep n8n down until the 10s automatic retry has also failed; the next one is 30s later,
    // which leaves a clear window for the manual "Retry now".
    await expect
      .poll(
        async () =>
          (await (await controller.request.get('/api/v1/integrations/webhook/deliveries')).json())[0]
            ?.attempts,
        { timeout: 60_000, intervals: [1_000] },
      )
      .toBeGreaterThanOrEqual(2)
  } finally {
    execSync(`docker start ${N8N_CONTAINER}`)
  }
  await expect.poll(n8nHealthy, { timeout: 90_000, intervals: [2_000] }).toBe(true)
  await controller.waitForTimeout(4_000) // n8n registers webhooks just after it reports healthy
  await controller.reload()
  await controller.getByRole('button', { name: 'Retry now' }).click()
  await expect(controller.getByText('Healthy')).toBeVisible({ timeout: 30_000 })
  await expect(controller.getByText(/^Delivered invoice/)).toBeVisible()
  await shot(controller, '08-integrations-recovered')

  // 9. Reconciliation results for the demo bank statement
  await clerk.goto('/reconciliation')
  const report = clerk.waitForResponse((r) => r.url().includes('/reconciliation/report/') && r.ok(), {
    timeout: 180_000,
  })
  await clerk
    .locator('input[type="file"]')
    .setInputFiles(path.join(DEMO, 'demo_statement_seeded.csv'))
  await report
  await shot(clerk, '09-reconciliation-results')
})
