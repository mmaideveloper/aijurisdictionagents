import { test, expect } from '@playwright/test';

test('health endpoint is healthy', async ({ request, baseURL }) => {
  const response = await request.get(`${baseURL}/health`);
  expect(response.ok()).toBeTruthy();
  await expect(response.json()).resolves.toEqual({ status: 'ok' });
});
