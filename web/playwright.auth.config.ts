import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: ["auth-bootstrap.spec.ts", "reading-plan-workspace.spec.ts", "citation-audit-workspace.spec.ts", "citation-audit-upload.spec.ts", "citation-audit-versions.spec.ts", "citation-audit-parsing.spec.ts", "document-outline-workspace.spec.ts", "confirmed-notes-workspace.spec.ts", "counter-evidence.spec.ts", "privacy-workspace.spec.ts", "page-mapping-workspace.spec.ts", "catalog-search.spec.ts", "discovery-evidence.spec.ts", "opinion-search-entry.spec.ts"],
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  outputDir: "test-results/auth-bootstrap",
  use: {
    baseURL: process.env.AUTH_E2E_BASE_URL ?? "http://127.0.0.1:13150",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
