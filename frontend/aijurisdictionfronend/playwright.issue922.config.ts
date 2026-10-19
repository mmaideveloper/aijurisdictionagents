import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e", testMatch: "issue-922-encrypted-export.spec.ts", workers: 1,
  timeout: 360000, expect: { timeout: 30000 }, reporter: "list",
  outputDir: "../../runs/issue922/playwright",
  use: { actionTimeout: 30000, navigationTimeout: 30000, baseURL: "http://127.0.0.1:5192", viewport: { width: 1600, height: 1100 }, trace: "off", video: "off", screenshot: "off" },
});
