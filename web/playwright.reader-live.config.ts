import {defineConfig} from "@playwright/test";
export default defineConfig({
  testDir:"./tests", testMatch:"reader-live-layout-audit.spec.ts", timeout:180_000,
  workers:1,retries:0,reporter:[["list"],["junit",{outputFile:"../output/playwright/v306-reader-production-before/results.xml"}]],
  outputDir:"../output/playwright/v306-reader-production-before/artifacts",
  use:{baseURL:process.env.READER_AUDIT_BASE_URL ?? "https://books.winstonmo.com",headless:true,trace:"retain-on-failure",screenshot:"only-on-failure"},
});
