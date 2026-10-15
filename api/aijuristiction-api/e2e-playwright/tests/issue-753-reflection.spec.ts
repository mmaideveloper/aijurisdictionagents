import { expect, test } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { randomUUID } from 'node:crypto';

// Real-service acceptance only. Run scripts/run_issue_753_e2e.py to prepare the
// synthetic PostgreSQL fixture, real provider, MCP, API and frontend.
test('a real draft is critiqued and revised visibly in the frontend', async ({ page, request }) => {
  test.setTimeout(600_000);
  const fixture = JSON.parse(readFileSync(resolve('../../../runs/e2e/issue-753/active.json'), 'utf8'));
  const api = process.env.API_BASE_URL ?? 'http://127.0.0.1:8083';
  const frontend = process.env.FRONTEND_BASE_URL ?? 'http://127.0.0.1:5173';
  expect(new URL(api).hostname).toMatch(/^(127\.0\.0\.1|localhost)$/);
  expect(new URL(frontend).hostname).toMatch(/^(127\.0\.0\.1|localhost)$/);
  const headers = { 'x-api-key': 'aijuris' };
  const title = `[${fixture.runId}] Synthetic reflection payment`;
  let caseId = '';
  let workflowRunId = '';
  await page.addInitScript(() => localStorage.setItem('aj_frontend_lang', 'en'));
  try {
    await page.goto(`${frontend}/auth`);
    await page.getByLabel('Work email').fill(fixture.email);
    await page.getByLabel('Password').fill(process.env.JURISDIGTA_E2E_TEST_USER_PASSWORD ?? '');
    await page.getByRole('button', { name: 'Sign in' }).click();
    const otp = page.getByLabel('OTP code');
    if (await otp.waitFor({ state: 'visible', timeout: 5000 }).then(() => true).catch(() => false)) {
      await otp.fill('111111'); // Isolated loopback LOCAL_AUTH_ACCEPT_ANY_CODE fixture.
      await page.getByRole('button', { name: 'Sign in' }).click();
    }
    await expect(page).toHaveURL(/\/app\/assistant/, { timeout: 30_000 });
    await page.getByRole('button', { name: 'My Profile', exact: true }).click();
    for (const label of [
      'Allow necessary case content to be sent to an approved external AI provider',
      'Allow necessary facts to be sent to external verification tools; per-run approval is also required',
    ]) {
      const consent = page.getByLabel(label, { exact: true });
      if (!await consent.isChecked()) {
        await consent.click();
        await expect(page.getByText('Privacy settings saved.', { exact: true })).toBeVisible();
      }
      await expect(consent).toBeChecked();
    }
    await page.goto(`${frontend}/app/case`);
    await page.getByLabel('Case name').fill(title);
    await page.getByLabel('Jurisdiction').fill('Slovakia');
    await page.getByLabel('Opposing party').fill('Synthetic B');
    const createdCase = page.waitForResponse(response => response.url() === `${api}/v1/cases` && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Start AI lawyer chat' }).click();
    expect((await createdCase).status()).toBe(201);
    caseId = (await (await createdCase).json()).case_id;
    const cases = await request.get(`${api}/v1/cases?user_id=${fixture.userId}`, { headers });
    expect(cases.ok()).toBeTruthy();
    expect((await cases.json()).some((item: {case_id: string}) => item.case_id === caseId)).toBe(true);
    await expect(page.locator('.case-item').filter({ hasText: title }).first()).toBeVisible({ timeout: 20_000 });
    const send = async (text: string) => {
      const composer = page.getByPlaceholder('Ask for legal research or document preparation...');
      await expect(composer).toBeEnabled({ timeout: 180_000 });
      const sendButton = page.getByRole('button', { name: 'Send message' });
      await expect(async () => {
        await composer.fill(text);
        await expect(composer).toHaveValue(text);
        await expect(sendButton).toBeEnabled();
      }).toPass({ timeout: 30_000 });
      const delivered = page.waitForResponse(response => response.url().includes('/stream') && response.request().method() === 'POST', { timeout: 180_000 });
      await sendButton.click({ timeout: 30_000 });
      const body = await (await delivered).text();
      const match = body.match(/"workflow_run_id"\s*:\s*"([^"]+)"/);
      if (match) workflowRunId = match[1];
      await expect(composer).toBeEnabled({ timeout: 180_000 });
    };
    const prepared = await request.post(`${api}/v1/case-workflows/runs`, { headers, data: {
      case_id: caseId, session_id: randomUUID(), user_id: fixture.userId, jurisdiction: 'SK', language: 'sk-SK',
      case_type_key: 'sk.civil.payment_confirmation', routing_confidence: 1,
      request_text: 'Priprav iba tento krátky plain-text návrh potvrdenia o zaplatení, bez ďalších polí: '
        + '"Synthetic A zaplatil Synthetic B sumu 100 EUR dňa 2026-10-15. '
        + 'Účel: synthetic loan repayment. Návrh bol vytvorený pomocou AI a pred použitím vyžaduje ľudskú kontrolu. '
        + 'Podpis príjemcu: __________". Ide výlučne o syntetický test. '
        + 'Iba v prvom návrhu pridaj samostatný riadok s doslovnou značkou [PRVY_NAVRH]. '
        + 'Táto značka označuje prvotný pracovný návrh; pri revízii ju odstráň. '
        + 'Ostatné overené hodnoty použi doslovne. Nepridávaj ďalšie zástupné polia ani externé kontroly.',
      facts: { payer_identification: 'Synthetic A', recipient_identification: 'Synthetic B',
        payment_date: '2026-10-15', payment_purpose: 'synthetic loan repayment' },
    } });
    expect(prepared.ok()).toBeTruthy();
    const waiting = await prepared.json();
    expect(waiting.pending_action.field).toBe('amount');
    workflowRunId = waiting.workflow_run_id;
    await send('100 EUR');
    let run: any;
    for (let step = 0; step < 2; step++) {
      const response = await request.get(`${api}/v1/case-workflows/runs/${workflowRunId}?user_id=${fixture.userId}`, { headers });
      expect(response.ok()).toBeTruthy();
      run = await response.json();
      if (run.status !== 'waiting_for_user') break;
      expect(run.pending_action.type).toBe('tool_consent');
      await send('No');
    }
    const auditResponse = await request.get(`${api}/v1/case-workflows/runs/${workflowRunId}/events?user_id=${fixture.userId}`, { headers });
    expect(auditResponse.ok()).toBeTruthy();
    const observedEvents = (await auditResponse.json()).items;
    if (run.status !== 'completed' && fixture.syntheticOnly === true) {
      writeFileSync(join(fixture.evidence, 'failed-synthetic-draft.txt'), run.final_answer);
    }
    writeFileSync(join(fixture.evidence, 'observed-run.json'), JSON.stringify({
      status: run.status, terminationReason: run.termination_reason, revisions: run.retry_count,
      reviews: run.review_decisions,
      events: observedEvents.map((event: any) => ({ type: event.event_type, status: event.status,
        category: event.details.failure_category ?? event.details.reason ?? '',
        revision: event.details.revision, provider: event.details.provider, model: event.details.model })),
    }, null, 2));
    expect(run.graph_version).toBe(5);
    expect(run.status).toBe('completed');
    expect(run.retry_count).toBeGreaterThan(0);
    expect(run.retry_count).toBeLessThanOrEqual(run.max_revision_attempts);
    await expect(page.getByText(/počet revízií|revisions:/).last()).toBeVisible();
    await expect(page.locator('.assistant-message').last()).toContainText('100 EUR');
    expect(run.presentation.citations).toContain(fixture.sourceId);
    await expect(page.locator('.assistant-presentation__citations').last()).toContainText(fixture.sourceId);
    const eventsResponse = await request.get(`${api}/v1/case-workflows/runs/${workflowRunId}/events?user_id=${fixture.userId}`, { headers });
    expect(eventsResponse.ok()).toBeTruthy();
    const events = (await eventsResponse.json()).items;
    expect(events.some((event: any) => event.event_type === 'output_critique_recorded')).toBe(true);
    const drafts = events.filter((event: any) => event.event_type === 'documents_drafted');
    expect(drafts.length).toBeGreaterThan(1);
    for (const draft of drafts) {
      expect(draft.details.provider).not.toMatch(/mock|deterministic|unspecified/);
      expect(draft.details.model).toBe(process.env.E2E_AZURE_FOUNDRY_DEPLOYMENT);
    }
    const retrieved = events.find((event: any) => event.event_type === 'legal_requirements_retrieved');
    expect(retrieved.details.source_ids).toContain(fixture.sourceId);
    const screenshot = join(fixture.evidence, 'reflection-final.png');
    await page.getByText(/počet revízií|revisions:/).last().scrollIntoViewIfNeeded();
    await page.screenshot({ path: screenshot, fullPage: true });
    // A PDF is generated by this scenario, so retain it and verify its actual
    // structure/text in the Python runner before declaring final acceptance.
    const artifact = run.artifacts[0];
    const pdf = await request.get(`${api}/v1/case-workflows/runs/${workflowRunId}/artifacts/${encodeURIComponent(artifact.artifact_id)}/pdf?user_id=${fixture.userId}`, { headers });
    expect(pdf.ok()).toBeTruthy();
    writeFileSync(join(fixture.evidence, 'reflection.pdf'), await pdf.body());
    writeFileSync(join(fixture.evidence, 'result-manifest.json'), JSON.stringify({
      schemaVersion: 1, runId: fixture.runId, syntheticOnly: true, workflowRunId,
      services: ['frontend', 'api', 'mcp', 'postgresql-api', 'postgresql-laws', 'azure-foundry'],
      expectedSourceId: fixture.sourceId, observedSourceIds: retrieved.details.source_ids,
      revisions: run.retry_count, routes: drafts.map((item: any) => ({ provider: item.details.provider, model: item.details.model })),
      screenshot: 'reflection-final.png', browserResult: 'passed', pdfValidation: 'pending',
      retention: 'Delete ignored evidence within seven days',
    }, null, 2));
  } finally {
    await page.locator('input[type="password"], input[inputmode="numeric"]').evaluateAll(inputs => {
      inputs.forEach(input => { (input as HTMLInputElement).value = ''; });
    });
    await page.screenshot({ path: join(fixture.evidence, 'final-state.png'), fullPage: true,
      mask: [page.locator('input[type="password"]'), page.locator('input[inputmode="numeric"]')] });
    if (caseId) {
      const deleted = await request.delete(`${api}/v1/cases/${caseId}?user_id=${fixture.userId}`, { headers });
      expect(deleted.ok()).toBeTruthy();
    }
  }
});
