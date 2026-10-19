import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  testIgnore: "private-banks.spec.ts",
  timeout: 180000,
  workers: 1,
  retries: 0,
  reporter: "line",
  outputDir: "../../runs/issue840/playwright",
  use: {
    baseURL: "http://127.0.0.1:8410",
    ...(process.platform === "win32" ? { channel: "msedge" } : {}),
    headless: true,
    trace: "off",
    screenshot: "off",
    video: "off",
  },
});
