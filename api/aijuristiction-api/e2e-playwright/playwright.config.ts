import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  use: {
    baseURL: process.env.API_BASE_URL ?? 'http://127.0.0.1:8080',
  },
  reporter: 'list',
});
