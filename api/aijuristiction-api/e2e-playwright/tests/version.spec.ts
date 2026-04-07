import { expect, test } from '@playwright/test';
import { ensureLiveApiOrFail } from './helpers/liveApi';

test.beforeEach(async ({ request, baseURL }) => {
  await ensureLiveApiOrFail(request, baseURL);
});

test('version endpoint returns service name semantic version and country law metadata', async ({ request, baseURL }) => {
  const response = await request.get(`${baseURL}/version`);
  expect(response.ok()).toBeTruthy();

  const payload = (await response.json()) as {
    service: string;
    version: string;
    laws_by_country?: Record<string, { country_code?: string; last_law_update_date?: string | null }>;
  };
  expect(payload.service).toBe('aijuristiction-api');
  expect(payload.version).toMatch(/^\d+\.\d+\.\d+$/);
  expect(payload.laws_by_country).toBeTruthy();
  expect(payload.laws_by_country?.sk?.country_code).toBe('SK');
});
