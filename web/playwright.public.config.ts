import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: "public-surface.spec.ts",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 1,
  reporter: [["list"]],
  outputDir: "test-results/public-surface",
  use: {
    baseURL: process.env.PUBLIC_BASE_URL ?? "https://books.winstonmo.com",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
