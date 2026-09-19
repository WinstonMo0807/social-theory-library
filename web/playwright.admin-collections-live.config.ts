import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests", testMatch: "admin-collections-v306-live.spec.ts",
  timeout: 60_000, expect: { timeout: 15_000 }, workers: 1, retries: 0,
  reporter: [["list"], ["junit", { outputFile: "test-results/admin-collections-v306-live.xml" }]],
  outputDir: "test-results/admin-collections-v306-live",
  use: { baseURL: process.env.CATALOGING_E2E_BASE_URL ?? "http://127.0.0.1:3105", headless: true, trace: "retain-on-failure", screenshot: "only-on-failure" },
  // The root task owns the disposable API and built preview. Never start a
  // second test DB/server or connect these scenarios to a production origin.
});
