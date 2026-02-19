import { defineConfig } from '@playwright/test';

const baseURL = process.env.API_BASE_URL ?? 'http://127.0.0.1:8080';

const wantsAutoStart = process.env.PW_START_API === '1' || !process.env.API_BASE_URL;
const enableWebServer = wantsAutoStart;

export default defineConfig({
  testDir: './tests',
  use: {
    baseURL,
  },
  reporter: 'list',
  webServer: enableWebServer
    ? {
        command: 'node ./scripts/start-api.mjs',
        url: `${baseURL}/health`,
        reuseExistingServer: true,
        timeout: 120_000,
        stdout: 'pipe',
        stderr: 'pipe',
      }
    : undefined,
});
