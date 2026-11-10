import { defineConfig } from '@playwright/test'

// Start the local API, Vite, and Docker database before running these tests.
export default defineConfig({
  testDir: './tests/browser',
  timeout: 90000,
  expect: { timeout: 15000 },
  workers: 1,
  reporter: 'list',
  outputDir: '.local/browser-results',
  use: { actionTimeout: 15000, baseURL: 'http://127.0.0.1:5173', viewport: { width: 1600, height: 1050 } },
})
