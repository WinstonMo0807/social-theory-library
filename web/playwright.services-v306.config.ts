import { defineConfig } from "@playwright/test";

// Synthetic NAS service stack only. No production API or reader data.
export default defineConfig({
  testDir: "./tests", testMatch: "cataloging-services-acceptance.spec.ts",
  timeout: 240_000, expect: { timeout: 20_000 }, workers: 1, retries: 0,
  reporter: [["list"], ["junit", { outputFile: "test-results/v306-services/results.xml" }]],
  outputDir: "test-results/v306-services/artifacts",
  use: {
    baseURL: "http://127.0.0.1:3106", headless: true, actionTimeout: 20_000, navigationTimeout: 45_000, trace: "on", video: "on", screenshot: "only-on-failure",
    // The isolated S3 protocol fixture has a dedicated seven-day certificate.
    // Trust that exact public key only; do not disable general TLS validation.
    launchOptions: { args: ["--no-proxy-server", "--host-resolver-rules=MAP stl-v306-test-s3 192.168.5.6", ...(process.env.V306_TEST_S3_SPKI ? [`--ignore-certificate-errors-spki-list=${process.env.V306_TEST_S3_SPKI}`] : [])] },
  },
  webServer: [{
    command: "node ../scripts/v306_service_e2e_proxy.mjs",
    url: "http://127.0.0.1:8106/api/ready/", timeout: 30_000, reuseExistingServer: false,
  }, {
    command: "npm run start -- --port 3106 --hostname 127.0.0.1",
    url: "http://127.0.0.1:3106/login", timeout: 120_000, reuseExistingServer: false,
    env: { INTERNAL_API_URL: "http://192.168.5.6:18106/api", INTERNAL_API_TOKEN: "isolated-v306-ssr-only-not-for-production", ALLOW_DEMO_FALLBACK: "false", NO_PROXY: "127.0.0.1,localhost,192.168.5.6" },
  }],
});
