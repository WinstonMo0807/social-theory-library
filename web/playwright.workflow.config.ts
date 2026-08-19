import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: "admin-workflow-v280.spec.ts",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  outputDir: "test-results/admin-workflow-v280",
  use: {
    baseURL: process.env.WORKFLOW_E2E_BASE_URL ?? "http://localhost:3100",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
