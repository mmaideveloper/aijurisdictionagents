import { test, expect } from '@playwright/test';
import { ensureLiveApiOrFail } from './helpers/liveApi';

test.beforeEach(async ({ request, baseURL }) => {
  await ensureLiveApiOrFail(request, baseURL);
});

test('health endpoint is healthy', async ({ request, baseURL }) => {
  const response = await request.get(`${baseURL}/health`);
  expect(response.ok()).toBeTruthy();
  await expect(response.json()).resolves.toMatchObject({
    status: 'ok',
    service: 'aijuristiction-api',
    llm: { status: 'ok' },
    database: { status: 'ok' },
  });
});
