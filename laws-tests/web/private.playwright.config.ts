import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  testMatch: "private-banks.spec.ts",
  workers: 1,
  retries: 0,
  outputDir: "../../runs/issue924/playwright",
  reporter: "line",
  use: {
    ...(process.platform === "win32" ? { channel: "msedge" } : {}),
    headless: true,
    actionTimeout: 20000,
    trace: "off",
    video: "off",
    screenshot: "off",
  },
});
