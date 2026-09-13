import { test, expect } from '@playwright/test';
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const root = path.resolve('../..');
const evidence = path.join(root, 'runs/chat-upload-804');
test.skip(process.env.VITE_API_BASE_URL !== 'http://127.0.0.1:8180', 'Requires the isolated local task 804 launcher.');
test.use({ trace: 'off', screenshot: 'off', video: 'off', viewport: { width: 1500, height: 1000 } });
test.setTimeout(240_000);

test('authenticated composer upload persists processed files in the selected case', async ({ page, request }) => {
  const input = JSON.parse(readFileSync(path.join(evidence, 'input.json'), 'utf8'));
  expect(input.syntheticOnly).toBe(true);
  expect(process.env.VITE_API_BASE_URL).toBe('http://127.0.0.1:8180');
  const password = process.env.JURISDIGTA_E2E_TEST_USER_PASSWORD;
  expect(Boolean(password)).toBe(true);
  const headers = { 'x-api-key': 'aijuris' };
  const list = await request.get(`http://127.0.0.1:8180/v1/cases?user_id=${input.userId}`, { headers });
  expect(list.ok()).toBe(true);
  expect((await list.json()).some((item: {case_id: string}) => item.case_id === input.caseId)).toBe(true);
  await page.addInitScript(() => {
    localStorage.setItem('aj_frontend_lang', 'en');
    localStorage.setItem('jurisdigta.web.auth.device.v1', 'upload804-device');
  });
  await page.goto(`/case/${input.caseId}`);
  await page.locator('input[type=email]').fill(input.email);
  await page.locator('input[type=password]').fill(password!);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.locator('.assistant-composer__input')).toBeVisible({ timeout: 30_000 });
  const selectedCase = page.locator('.case-item').filter({ hasText: 'Synthetic chat document upload 804' });
  await expect(selectedCase).toBeVisible();
  await selectedCase.click();
  await expect(selectedCase).toHaveClass(/active/);
  await expect(page.locator('.assistant-model-disclosure')).toContainText('gpt-4o-mini');
  const routeResponse = await request.get(`http://127.0.0.1:8180/v1/model-routing/effective?user_id=${input.userId}`, { headers });
  expect(routeResponse.ok()).toBe(true);
  const route = await routeResponse.json();
  expect(route.provider).not.toBe('mock');
  expect(route.model).toBe('gpt-4o-mini');
  const upload = page.getByRole('button', { name: 'Upload documents to this case' });
  await expect(upload).toBeVisible();
  await upload.focus();
  await expect(upload).toBeFocused();
  mkdirSync(evidence, { recursive: true });
  await page.screenshot({ path: path.join(evidence, '01-upload-icon.png'), fullPage: true });
  const chooserEvent = page.waitForEvent('filechooser');
  await page.keyboard.press('Enter');
  const chooser = await chooserEvent;
  expect(chooser.isMultiple()).toBe(true);
  const name = `${input.runId}-${Date.now()}-contract.txt`;
  await page.locator('.assistant-composer__input').fill('Keep this draft while importing.');
  await chooser.setFiles({ name, mimeType: 'text/plain', buffer: Buffer.from('Synthetic purchase contract. Item: test table. Agreed price: 804 EUR. Reference: UPLOAD804TABLE. Human review required.') });
  await expect(page.locator('.assistant-composer__status')).toContainText(name);
  await expect(page.locator('.assistant-composer__input')).toBeEnabled();
  await page.screenshot({ path: path.join(evidence, '02-import-pending.png'), fullPage: true });
  await expect.poll(async () => {
    const response = await request.get(`http://127.0.0.1:8180/v1/cases/${input.caseId}/history?user_id=${input.userId}`, { headers });
    const history = await response.json();
    return history.documents?.find((doc: { original_filename: string }) => doc.original_filename === name)?.processing_status;
  }, { timeout: 180_000 }).toBe('processed');
  await expect(page.locator('.assistant-composer__status')).toContainText('ready for semantic search');
  await expect(page.locator('.assistant-composer__input')).toHaveValue('Keep this draft while importing.');
  await page.screenshot({ path: path.join(evidence, '03-processed-document.png'), fullPage: true });
  writeFileSync(path.join(evidence, 'result.json'), JSON.stringify({ syntheticOnly: true, runId: input.runId,
    caseId: input.caseId, database: input.database, expectedFilename: name, observedStatus: 'processed',
    expectedProvider: 'azurefoundry', observedProvider: route.provider, observedModel: route.model,
    services: ['frontend:5189', 'API:8180', 'MCP:8170', 'PostgreSQL:5432'],
    scope: 'Authenticated browser upload, processing and preserved composer draft; semantic answer not tested',
    retentionDays: 7 }, null, 2));
});
