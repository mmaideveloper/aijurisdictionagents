import { defineConfig, devices } from "@playwright/test";

const port = process.env.MOBILE_E2E_PORT?.trim() || "7361";
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./tests",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: {
    baseURL,
    trace: "retain-on-failure"
  },
  webServer: {
    command: [
      "flutter build web",
      "--dart-define=AIJ_API_BASE_URL=http://127.0.0.1:8080",
      "--dart-define=AIJ_API_KEY=aijuris",
      "--dart-define=AIJ_DEFAULT_LANGUAGE=EN",
      "--dart-define=AIJ_SPEECH_MODE=local",
      `&& .\\e2e-playwright\\node_modules\\.bin\\http-server.cmd build/web -a 127.0.0.1 -p ${port} -c-1`
    ].join(" "),
    cwd: "..",
    url: baseURL,
    reuseExistingServer: false,
    timeout: 240_000
  },
  projects: [
    {
      name: "chromium-mobile",
      use: { ...devices["Pixel 7"] }
    }
  ]
});
