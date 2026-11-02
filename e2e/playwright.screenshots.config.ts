import { defineConfig, devices } from '@playwright/test'

// README screenshots against the local dev stack (make fresh + make frontend).
export default defineConfig({
  testDir: './screenshots',
  timeout: 10 * 60_000,
  workers: 1,
  retries: 0,
  reporter: 'list',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: process.env.SCREENSHOT_BASE_URL || 'http://localhost:5173',
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    actionTimeout: 30_000,
    navigationTimeout: 30_000,
  },
})
