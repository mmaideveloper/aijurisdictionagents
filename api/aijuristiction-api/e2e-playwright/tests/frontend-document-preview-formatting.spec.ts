import { expect, test, type Page } from '@playwright/test';

const frontendBaseURL = process.env.FRONTEND_BASE_URL;
const authSessionKey = 'jurisdigta.web.auth.user.v1';
const caseStorageKey = 'aijurisdictionfrontend.mock.cases.v1';

const assistantDraft = `LawyerSlovakia: USERT-FACING: Pripravujem splnomocnenie pre Emiliu Testovu na pouzivanie firemneho auta firmy ESolutions SK s.r.o. s nasledujucimi udajmi:

**Splnomocnenie**

**Splnomocnitel:**
Marek Matonok
ESolutions SK s.r.o.
Partizanska 665,
059 18 Spisske Bystre

**Splnomocnenec:**
Emilia Testova

**Predmet splnomocnenia:**
Pouzivanie firemneho auta firmy ESolutions SK s.r.o.

**SPZ vozidla:** PP472DT

**Doba platnosti splnomocnenia:**
Od 1. jula 2026 do 31. decembra 2026

Datum: 25. juna 2026
Podpis: ______________________`;

async function seedAuthenticatedMockCase(page: Page) {
  await page.route('**/v1/cases?**', async (route) => {
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Use mock case storage for this frontend rendering test.' }),
    });
  });

  await page.addInitScript(
    ({ authKey, storageKey, draft }) => {
      window.localStorage.setItem('aj_frontend_lang', 'en');
      window.sessionStorage.setItem(
        authKey,
        JSON.stringify({
          userId: 'document-preview-test-user',
          email: 'document-preview@example.test',
          name: 'Document Preview Test User',
          role: 'JurisDigta user',
        }),
      );
      window.localStorage.setItem(
        storageKey,
        JSON.stringify([
          {
            id: 'document-preview-case',
            title: 'Document preview formatting bug',
            description: 'Mock case for assistant document preview formatting.',
            status: 'In progress',
            createdAt: '2026-06-26T10:00:00.000Z',
            interactionHistory: [
              {
                id: 'document-preview-user-message',
                createdAt: '2026-06-26T10:00:01.000Z',
                actor: 'You',
                message: 'Priprav splnomocnenie pre firemne auto.',
              },
              {
                id: 'document-preview-assistant-message',
                createdAt: '2026-06-26T10:00:02.000Z',
                actor: 'AI Lawyer',
                message: draft,
              },
            ],
            selectedRole: 'AI Lawyer',
            selectedMode: 'Draft',
            selectedCommunicationMode: 'Chat',
            workspace: {
              meta: 'SK | 0 docs',
              objective: 'Verify assistant document preview formatting.',
              nextAction: 'Review generated draft preview.',
              jurisdiction: 'SK',
              output: 'Formatted document preview',
            },
            jurisdiction: 'SK',
            opposingParty: 'None',
            documents: [],
            source: 'mock',
          },
        ]),
      );
    },
    { authKey: authSessionKey, storageKey: caseStorageKey, draft: assistantDraft },
  );
}

test('assistant legal draft renders as formatted JurisDigta document preview', async ({ page }, testInfo) => {
  test.skip(!frontendBaseURL, 'Set FRONTEND_BASE_URL to run frontend document preview checks.');

  await page.setViewportSize({ width: 1146, height: 681 });
  await seedAuthenticatedMockCase(page);
  await page.goto(`${frontendBaseURL}/app/chat`);

  const caseButton = page.locator('.case-item').filter({ hasText: 'Document preview formatting bug' }).first();
  await expect(caseButton).toBeVisible({ timeout: 20_000 });
  await caseButton.click();

  await expect(page.getByText('Pripravujem splnomocnenie pre Emiliu Testovu')).toBeVisible();

  const preview = page.locator('.assistant-document-preview').first();
  await expect(preview).toBeVisible();
  await expect(preview.locator('.assistant-document-preview__letterhead span')).toHaveText('JurisDigta');
  await expect(preview.locator('.assistant-document-preview__letterhead small')).toHaveText('Document preview');
  await expect(preview.locator('.assistant-document-preview__page-marker')).toContainText('A4 preview 1');
  await expect(preview.getByRole('heading', { name: 'Splnomocnenie' })).toBeVisible();
  await expect(preview).toContainText('Marek Matonok');
  await expect(preview).toContainText('Emilia Testova');
  await expect(preview).toContainText('PP472DT');
  await expect(preview).not.toContainText('**');
  await expect(page.getByText(/USER[T]?-FACING/i)).toHaveCount(0);
  await expect(page.getByText('LawyerSlovakia')).toHaveCount(0);

  const sheetBox = await preview.locator('.assistant-document-preview__sheet').boundingBox();
  expect(sheetBox?.width ?? 0).toBeGreaterThan(520);
  expect(sheetBox?.height ?? 0).toBeGreaterThan(500);

  await testInfo.attach('jurisdigta-document-preview.png', {
    body: await page.screenshot({ fullPage: true }),
    contentType: 'image/png',
  });
});
