import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: "compact-editorial-density.spec.ts",
  timeout: 10 * 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  outputDir: "test-results/compact-editorial-density",
  use: {
    baseURL: process.env.DENSITY_BASE_URL ?? "http://localhost:13000",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
