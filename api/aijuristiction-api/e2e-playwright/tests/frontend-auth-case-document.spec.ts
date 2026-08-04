import { APIRequestContext, expect, Page, test } from '@playwright/test';
import { execFile } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';
import { ensureLiveApiOrFail } from './helpers/liveApi';

const execFileAsync = promisify(execFile);

const apiKey = process.env.API_KEY ?? 'aijuris';
const frontendBaseURL = process.env.FRONTEND_BASE_URL ?? 'http://127.0.0.1:5173';
const otpCode = process.env.E2E_OTP_CODE ?? '111111';

type AuthUser = {
  userId: string;
  email: string;
};

type CaseDocument = {
  doc_id: string;
  kind: string;
  original_filename: string;
  processing_status: string;
};

type CaseHistory = {
  messages: Array<{ role: string; content: string; agent_name: string | null }>;
  documents: CaseDocument[];
};

test.beforeEach(async ({ page, request, baseURL }) => {
  await ensureLiveApiOrFail(request, baseURL);
  await page.addInitScript(() => {
    window.localStorage.setItem('aj_frontend_lang', 'en');
  });
});

test('registration and login can create, reopen, and preview a generated potvrdenie PDF', async ({
  page,
  request,
  baseURL,
}, testInfo) => {
  test.setTimeout(300_000);
  const runId = Date.now();
  const registrationEmail = `playwright.${runId}@example.test`;
  const registrationPhone = `+421900${String(runId).slice(-6)}`;
  const caseTitle = `E2E potvrdenie ${runId}`;
  const prompt = [
    'Priprav potvrdenie o zaplatení podľa jednoduchého potvrdenia z chat simulátora.',
    'Suma: 1000 EUR.',
    'Platiteľ: Matej Mat, Stromová 10, Poprad.',
    'Príjemca: Matej Mat, Stromová 10, Poprad.',
    'Číslo občianskeho preukazu: 0800988MM.',
    'Rodné číslo: 08089/08089.',
    'Dátum prijatia: 1.1.2026.',
    'Splatné do: 1.1.2027.',
    'Vygeneruj finálne PDF potvrdenie na stiahnutie.',
  ].join(' ');
  await registerThroughUi(page, registrationEmail, registrationPhone);
  await logout(page);

  const user = await loginThroughUi(page, registrationEmail, 'tesT2026!');
  await deletePriorE2ECases(request, baseURL, user.userId);
  await createCaseThroughUi(page, caseTitle);
  await sendWorkspaceMessage(page, prompt);

  const createdCase = await findCaseByTitle(request, baseURL, user.userId, caseTitle);
  const history = await pollGeneratedDocument(request, baseURL, user.userId, createdCase.case_id);
  const generatedDocuments = history.documents.filter(
    (document) => document.kind === 'generated_document'
  );
  expect(generatedDocuments).toHaveLength(1);
  expect(generatedDocuments[0].original_filename).toMatch(/^potvrdenie.*_\d{8}T\d{6}Z\.pdf$/);

  const followupPrompts = [
    'Ake su chybajuce udaje?',
    'Aky je nazov modelu ktory pouzivam?',
    'Pouzivas lokalny MCP?',
  ];
  for (const followupPrompt of followupPrompts) {
    await sendWorkspaceMessage(page, followupPrompt);
  }

  const followupHistory = await pollFollowupAnswers(
    request,
    baseURL,
    user.userId,
    createdCase.case_id,
    followupPrompts,
  );
  expect(followupHistory.documents.filter((document) => document.kind === 'generated_document')).toHaveLength(1);
  const followupAnswers = answersFollowingPrompts(followupHistory, followupPrompts);
  expect(followupAnswers).toHaveLength(followupPrompts.length);
  for (const answer of followupAnswers) {
    expect(answer.toLowerCase()).not.toContain('tu je konecna verzia dokumentu');
    expect(answer.toLowerCase()).not.toContain('dokument je pripraveny na export');
  }

  await openSelectedCasePanel(page);
  await expect(page.locator('.sidebar-section--documents .sidebar-document-link')).toHaveCount(1);
  const documentLink = page
    .locator('.sidebar-section--documents .sidebar-document-link')
    .filter({ hasText: generatedDocuments[0].original_filename });
  await expect(documentLink).toBeVisible();

  const viewerPagePromise = page.context().waitForEvent('page');
  await documentLink.click();
  const viewerPage = await viewerPagePromise;
  await viewerPage.waitForLoadState('domcontentloaded');
  await expect(viewerPage).toHaveURL(/\/app\/documents\/view/);
  await expect(viewerPage.getByText(generatedDocuments[0].original_filename)).toBeVisible();
  const frame = viewerPage.locator('iframe.document-viewer-frame');
  await expect(frame).toBeVisible({ timeout: 30_000 });
  const frameBox = await frame.boundingBox();
  expect(frameBox?.height ?? 0).toBeGreaterThanOrEqual(1000);

  const pdf = await request.get(
    `${baseURL}/v1/cases/${createdCase.case_id}/documents/${generatedDocuments[0].doc_id}/pdf?user_id=${user.userId}`,
    { headers: { 'x-api-key': apiKey } }
  );
  expect(pdf.ok()).toBeTruthy();
  expect(pdf.headers()['content-type']).toContain('application/pdf');
  const pdfText = await extractPdfText(Buffer.from(await pdf.body()));
  expect(pdfText).toContain('JurisDigta');
  expect(pdfText).toMatch(/Potvrdenie/i);
  expect(pdfText).toContain('Platitel:');
  expect(pdfText).toContain('Prijemca:');
  expect(pdfText).toContain('1000');
  expect(pdfText).toContain('API version:');
  expect(pdfText).toContain('Core Version:');
  expect(pdfText).not.toContain('Spracovanie stale prebieha');
  expect(pdfText).not.toContain('Technicke');
  await viewerPage.close();

  await logout(page);
  await loginThroughUi(page, registrationEmail, 'tesT2026!');
  await selectExistingCase(page, caseTitle);
  await expect(page.getByText(prompt.slice(0, 70), { exact: false })).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('.assistant-message').filter({ hasText: /Potvrdenie|potvrdenie/i }).first()).toBeVisible({
    timeout: 20_000,
  });
  await openSelectedCasePanel(page);
  await expect(page.locator('.sidebar-section--documents .sidebar-document-link')).toHaveCount(1);
  await expect(page.locator('.sidebar-section--documents .sidebar-document-link').first()).toContainText(
    /potvrdenie.*\.pdf/
  );

  const hydratedMessages = page.locator('.assistant-message');
  await expect(hydratedMessages).toHaveCount(8, { timeout: 20_000 });
  await expect(hydratedMessages.last()).toContainText(/MCP/i);
  await hydratedMessages.nth(0).evaluate((element) => {
    (element as HTMLElement).style.display = 'none';
  });
  await hydratedMessages.nth(1).evaluate((element) => {
    (element as HTMLElement).style.display = 'none';
  });
  await page.addStyleTag({
    content: `
      .app-shell--assistant,
      .app-shell__body--assistant,
      .app-shell--assistant .main-content,
      .app-shell--assistant .workspace-page,
      .app-shell--assistant .workspace-shell,
      .app-shell--assistant .workspace-grid,
      .app-shell--assistant .workspace-center,
      .app-shell--assistant .assistant-workspace,
      .assistant-main,
      .assistant-thread,
      .assistant-thread__viewport {
        height: auto !important;
        max-height: none !important;
        overflow: visible !important;
      }
      .assistant-thread__viewport { flex: none !important; }
      .assistant-composer { display: none !important; }
    `,
  });
  const screenshotPath = testInfo.outputPath('issue-591-followup-routing.png');
  await page.screenshot({ path: screenshotPath, fullPage: true });
  await testInfo.attach('issue-591-followup-routing', {
    path: screenshotPath,
    contentType: 'image/png',
  });
});

async function registerThroughUi(page: Page, email: string, phone: string): Promise<void> {
  await page.goto(`${frontendBaseURL}/auth`);
  await page.getByRole('button', { name: 'Sign up' }).click();
  await page.getByLabel('Phone number').fill(phone);
  await page.getByLabel('Work email').fill(email);
  await page.getByLabel('Password').fill('tesT2026!');
  await page.getByRole('button', { name: 'Continue to email verification' }).click();
  await expect(page.getByText('OTP code was sent to the selected email.')).toBeVisible({ timeout: 15_000 });
  await page.getByLabel('OTP code').fill(otpCode);
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page).toHaveURL(/\/app\/assistant/, { timeout: 30_000 });
}

async function loginThroughUi(page: Page, email: string, password: string): Promise<AuthUser> {
  await page.goto(`${frontendBaseURL}/auth`);
  await page.getByLabel('Work email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();

  const otpInput = page.locator('form input[inputmode="numeric"]');
  if (await otpInput.waitFor({ state: 'visible', timeout: 5000 }).then(() => true).catch(() => false)) {
    await otpInput.fill(otpCode);
    await page.getByRole('button', { name: 'Sign in' }).click();
  }

  await expect(page).toHaveURL(/\/app\/assistant/, { timeout: 30_000 });
  const rawUser = await page.evaluate(() => window.sessionStorage.getItem('jurisdigta.web.auth.user.v1'));
  expect(rawUser).toBeTruthy();
  const parsed = JSON.parse(rawUser as string) as AuthUser;
  expect(parsed.email.toLowerCase()).toBe(email.toLowerCase());
  return parsed;
}

async function logout(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Log Out' }).click();
  await expect(page).toHaveURL(/\/auth/, { timeout: 10_000 });
}

async function createCaseThroughUi(page: Page, caseTitle: string): Promise<void> {
  await page.goto(`${frontendBaseURL}/app/case`);
  await page.getByLabel('Case name').fill(caseTitle);
  await page.getByLabel('Jurisdiction').fill('Slovakia');
  await page.getByLabel('Opposing party').fill('bez protistrany');
  await page.getByRole('button', { name: 'Start AI lawyer chat' }).click();
  await expect(page.locator('.case-item').filter({ hasText: caseTitle })).toBeVisible({ timeout: 20_000 });
}

async function sendWorkspaceMessage(page: Page, prompt: string): Promise<void> {
  const messages = page.locator('.assistant-message');
  const composer = page.getByPlaceholder('Ask for legal research or document preparation...');
  const sendButton = page.getByRole('button', { name: 'Send message' });
  await expect(composer).toBeEnabled({ timeout: 120_000 });
  await expect(async () => {
    await composer.fill(prompt);
    await expect(composer).toHaveValue(prompt);
    await expect(sendButton).toBeEnabled();
  }).toPass({ timeout: 60_000 });
  await sendButton.click();
  await expect(messages.filter({ hasText: prompt })).toBeVisible({ timeout: 30_000 });
  await expect
    .poll(
      async () => {
        const lastMessage = messages.last();
        const role = (await lastMessage.locator('.assistant-message__role').textContent())?.trim();
        const text = (await lastMessage.locator('.assistant-message__text').textContent())?.trim();
        return role !== 'You' && Boolean(text);
      },
      { timeout: 120_000 },
    )
    .toBe(true);
  await expect(composer).toBeEnabled({ timeout: 120_000 });
}

async function openSelectedCasePanel(page: Page): Promise<void> {
  const selectedCaseToggle = page.locator('.sidebar-section--selected-case .sidebar-section__toggle');
  await expect(selectedCaseToggle).toBeVisible({ timeout: 20_000 });
  const isExpanded = await selectedCaseToggle.getAttribute('aria-expanded');
  if (isExpanded !== 'true') {
    await selectedCaseToggle.click();
  }
}

async function selectExistingCase(page: Page, caseTitle: string): Promise<void> {
  await page.goto(`${frontendBaseURL}/app/chat`);
  const caseButton = page.locator('.case-item').filter({ hasText: caseTitle }).first();
  await expect(caseButton).toBeVisible({ timeout: 20_000 });
  await caseButton.click();
  await expect(caseButton).toHaveClass(/active/, { timeout: 20_000 });
}

async function findCaseByTitle(
  request: APIRequestContext,
  baseURL: string | undefined,
  userId: string,
  title: string
): Promise<{ case_id: string; title: string }> {
  const response = await request.get(`${baseURL}/v1/cases?user_id=${userId}`, {
    headers: { 'x-api-key': apiKey },
  });
  expect(response.ok()).toBeTruthy();
  const cases = (await response.json()) as Array<{ case_id: string; title: string }>;
  const match = cases.find((item) => item.title === title);
  expect(match).toBeTruthy();
  return match as { case_id: string; title: string };
}

async function deletePriorE2ECases(
  request: APIRequestContext,
  baseURL: string | undefined,
  userId: string
): Promise<void> {
  const response = await request.get(`${baseURL}/v1/cases?user_id=${userId}`, {
    headers: { 'x-api-key': apiKey },
  });
  expect(response.ok()).toBeTruthy();
  const cases = (await response.json()) as Array<{ case_id: string; title: string }>;
  for (const item of cases.filter((candidate) => candidate.title.startsWith('E2E potvrdenie'))) {
    const deleted = await request.delete(`${baseURL}/v1/cases/${item.case_id}?user_id=${userId}`, {
      headers: { 'x-api-key': apiKey },
    });
    expect(deleted.ok()).toBeTruthy();
  }
}

async function pollGeneratedDocument(
  request: APIRequestContext,
  baseURL: string | undefined,
  userId: string,
  caseId: string
): Promise<CaseHistory> {
  const deadline = Date.now() + 120_000;
  let lastHistory: CaseHistory | null = null;

  while (Date.now() < deadline) {
    const response = await request.get(
      `${baseURL}/v1/cases/${caseId}/history?user_id=${userId}&limit=200`,
      { headers: { 'x-api-key': apiKey } }
    );
    expect(response.ok()).toBeTruthy();
    lastHistory = (await response.json()) as CaseHistory;
    const generatedDocuments = lastHistory.documents.filter(
      (document) => document.kind === 'generated_document'
    );
    if (
      generatedDocuments.length === 1 &&
      /^potvrdenie.*_\d{8}T\d{6}Z\.pdf$/.test(generatedDocuments[0].original_filename) &&
      lastHistory.messages.some((message) => message.role === 'user') &&
      lastHistory.messages.some((message) => message.role === 'assistant')
    ) {
      return lastHistory;
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }

  throw new Error(`Generated potvrdenie PDF was not persisted. Last history: ${JSON.stringify(lastHistory)}`);
}

async function pollFollowupAnswers(
  request: APIRequestContext,
  baseURL: string | undefined,
  userId: string,
  caseId: string,
  prompts: string[],
): Promise<CaseHistory> {
  const deadline = Date.now() + 180_000;
  let lastHistory: CaseHistory | null = null;

  while (Date.now() < deadline) {
    const response = await request.get(
      `${baseURL}/v1/cases/${caseId}/history?user_id=${userId}&limit=200`,
      { headers: { 'x-api-key': apiKey } },
    );
    expect(response.ok()).toBeTruthy();
    lastHistory = (await response.json()) as CaseHistory;
    if (answersFollowingPrompts(lastHistory, prompts).length === prompts.length) {
      return lastHistory;
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }

  throw new Error(`Follow-up answers were not persisted. Last history: ${JSON.stringify(lastHistory)}`);
}

function answersFollowingPrompts(history: CaseHistory, prompts: string[]): string[] {
  const answers: string[] = [];
  for (const prompt of prompts) {
    const promptIndex = history.messages.findIndex(
      (message) => message.role === 'user' && message.content === prompt,
    );
    if (promptIndex < 0) {
      continue;
    }
    const answer = history.messages
      .slice(promptIndex + 1)
      .find((message) => message.role === 'assistant');
    if (answer) {
      answers.push(answer.content);
    }
  }
  return answers;
}

async function extractPdfText(pdf: Buffer): Promise<string> {
  const tempDir = await mkdtemp(path.join(tmpdir(), 'jurisdigta-pdf-'));
  const pdfPath = path.join(tempDir, 'document.pdf');
  await writeFile(pdfPath, pdf);
  const script = [
    'from pypdf import PdfReader',
    'import sys',
    'reader = PdfReader(sys.argv[1])',
    'print("\\n".join(page.extract_text() or "" for page in reader.pages))',
  ].join('\n');
  const candidates = [
    process.env.PYTHON,
    path.resolve(process.cwd(), '..', '..', '..', 'conda', 'python.exe'),
    'python',
  ].filter(Boolean) as string[];
  let lastError = '';

  try {
    for (const candidate of candidates) {
      try {
        const { stdout } = await execFileAsync(candidate, ['-c', script, pdfPath], {
          encoding: 'utf8',
          env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
          maxBuffer: 2_000_000,
        });
        return stdout;
      } catch (error) {
        lastError = error instanceof Error ? error.message : String(error);
        continue;
      }
    }
    throw new Error(`No Python runtime with pypdf was available to inspect the generated PDF. Last error: ${lastError}`);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}
