import { defineConfig } from "@playwright/test";
import { resolve } from "node:path";

const python = resolve("..", ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const fixtureServer = resolve("..", "scripts", "local_cataloging_e2e_api.py");

export default defineConfig({
  testDir: "./tests", testMatch: ["cataloging-session-v305.spec.ts", "person-resolution-v305.spec.ts", "scholar-portrait-v305.spec.ts"],
  timeout: 60_000, expect: { timeout: 15_000 }, workers: 1, retries: 0,
  reporter: [["list"]], outputDir: "test-results/cataloging-v305",
  use: { baseURL: "http://127.0.0.1:3105", headless: true, trace: "retain-on-failure", screenshot: "only-on-failure" },
  webServer: [
    {
      command: `"${python}" "${fixtureServer}"`,
      url: "http://127.0.0.1:8105/api/ready/", timeout: 120_000, reuseExistingServer: false,
    },
    {
      command: "npm run start -- --port 3105 --hostname 127.0.0.1",
      url: "http://127.0.0.1:3105/login", timeout: 120_000, reuseExistingServer: false,
      env: { INTERNAL_API_URL: "http://127.0.0.1:8105/api", INTERNAL_API_TOKEN: "local-e2e-server-token-305-not-for-production", ALLOW_DEMO_FALLBACK: "false", NO_PROXY: "127.0.0.1,localhost" },
    },
  ],
});
