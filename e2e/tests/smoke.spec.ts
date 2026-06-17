import { expect, test } from '@playwright/test'

test.describe('FinFlow smoke', () => {
  test('login page renders', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByRole('heading', { name: 'Welcome to FinFlow' })).toBeVisible()
    await expect(page.getByLabel('Email')).toBeVisible()
    await expect(page.getByLabel('Password')).toBeVisible()
  })

  test('controller can sign in and reach dashboard', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel('Email').fill('controller@acmecorp.com')
    await page.getByLabel('Password').fill('Test1234!')
    await page.getByRole('button', { name: 'Sign in' }).click()

    await expect(page).toHaveURL('/')
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible({
      timeout: 15_000,
    })
  })

  test('authenticated user can open invoices and reconciliation', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel('Email').fill('controller@acmecorp.com')
    await page.getByLabel('Password').fill('Test1234!')
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page).toHaveURL('/')

    await page.getByRole('link', { name: 'Invoices' }).click()
    await expect(page).toHaveURL('/invoices')
    await expect(page.getByRole('heading', { name: 'Invoices' })).toBeVisible()

    await page.getByRole('link', { name: 'Reconciliation' }).click()
    await expect(page).toHaveURL('/reconciliation')
    await expect(page.getByRole('heading', { name: 'Bank Reconciliation' })).toBeVisible()
  })
})
