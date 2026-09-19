import { defineConfig } from "@playwright/test";
import cataloging from "./playwright.cataloging.config";

// Reuses the repository's isolated API, dummy fixture accounts and SSR
// transport configuration. No production database, reader record or service.
export default defineConfig({
  ...cataloging,
  testMatch: ["*v306.spec.ts", "*v306-live.spec.ts", "cataloging-session-v305.spec.ts"],
  reporter: [["list"], ["junit", { outputFile: "test-results/v306/results.xml" }]],
  outputDir: "test-results/v306/artifacts",
});
