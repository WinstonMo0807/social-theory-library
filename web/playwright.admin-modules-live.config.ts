import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests", testMatch: ["admin-module-matrix-v306-live.spec.ts", "admin-route-layout-v306-live.spec.ts"],
  timeout: 90_000, expect: { timeout: 15_000 }, workers: 1, retries: 0,
  reporter: [["list"], ["junit", { outputFile: "test-results/admin-modules-v306-live.xml" }]],
  outputDir: "test-results/admin-modules-v306-live",
  use: { baseURL: "http://127.0.0.1:3105", headless: true, trace: "retain-on-failure", screenshot: "only-on-failure" },
  // Root task owns the one disposable API + preview. No production baseURL.
});
