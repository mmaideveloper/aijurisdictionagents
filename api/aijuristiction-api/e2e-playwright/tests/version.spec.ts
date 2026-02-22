import { expect, test } from '@playwright/test';
import { ensureLiveApiOrFail } from './helpers/liveApi';

test.beforeEach(async ({ request, baseURL }) => {
  await ensureLiveApiOrFail(request, baseURL);
});

test('version endpoint returns service name and semantic version', async ({ request, baseURL }) => {
  const response = await request.get(`${baseURL}/version`);
  expect(response.ok()).toBeTruthy();

  const payload = (await response.json()) as { service: string; version: string };
  expect(payload.service).toBe('aijuristiction-api');
  expect(payload.version).toMatch(/^\d+\.\d+\.\d+$/);
});
