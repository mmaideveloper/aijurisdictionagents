import { defineConfig, devices } from "@playwright/test";

const port = process.env.CORPORATE_WEB_E2E_PORT?.trim() || "8001";
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  expect: {
    timeout: 10_000
  },
  reporter: [["list"]],
  use: {
    baseURL,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    video: "off"
  },
  webServer: {
    command: `node e2e/static-server.mjs ${port}`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 30_000
  },
  projects: [
    {
      name: "acceptance",
      use: { ...devices["Desktop Chrome"] }
    },
    {
      name: "reproduction",
      use: { ...devices["Desktop Chrome"] }
    }
  ]
});
