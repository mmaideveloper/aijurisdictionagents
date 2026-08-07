import { expect, test, type Page, type Route, type TestInfo } from '@playwright/test';

const frontendBaseURL = process.env.FRONTEND_BASE_URL;
const authSessionKey = 'jurisdigta.web.auth.user.v1';
const userId = 'admin-local-model-e2e-user';
const userEmail = 'admin-local-model@example.test';
const caseId = 'admin-local-model-case';
const sessionId = '44444444-4444-4444-8444-444444444444';
const now = '2026-07-24T09:00:00.000Z';
const selectedModelProfileId = 'local_ollama_qwen4b';
const selectedModelLabel = 'Local Ollama - qwen3:4b';
const defaultModelLabel = 'Local Ollama - qwen3:1.7b';
const draftingPrompt =
  'Prepare a Slovak draft power of attorney for operating a company vehicle for ESolutions SK s.r.o.';
const draftingAnswer = [
  'Splnomocnenie je pripravene na zaklade vybraneho lokalneho modelu Local Ollama - qwen3:4b.',
  '',
  'Splnomocnitel: ESolutions SK s.r.o.',
  'Splnomocnenec: Emilia Testova.',
  'Predmet: pouzivanie firemneho vozidla.',
].join('\n');

type ChatHistoryMessage = {
  communication_id: string;
  role: string;
  content: string;
  agent_name: string | null;
  created_at: string;
  citations: unknown[];
};

type SessionUser = {
  userId?: string;
  email: string;
  name: string;
  role: string;
};

async function seedSessionUser(page: Page, user: SessionUser) {
  await page.addInitScript(
    ({ key, userData }) => {
      window.localStorage.setItem('aj_frontend_lang', 'en');
      window.sessionStorage.setItem(
        key,
        JSON.stringify({
          ...(userData.userId ? { userId: userData.userId } : {}),
          email: userData.email,
          name: userData.name,
          role: userData.role,
        }),
      );
    },
    { key: authSessionKey, userData: user },
  );
}

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

function completedMessages(promptSent: boolean): ChatHistoryMessage[] {
  if (!promptSent) {
    return [];
  }

  return [
    {
      communication_id: 'admin-local-model-user-message',
      role: 'user',
      content: draftingPrompt,
      agent_name: null,
      created_at: now,
      citations: [],
    },
    {
      communication_id: 'admin-local-model-assistant-message',
      role: 'assistant',
      content: draftingAnswer,
      agent_name: 'LawyerSlovakia',
      created_at: now,
      citations: [],
    },
  ];
}

async function askAssistant(page: Page, prompt: string) {
  await page.getByPlaceholder('Ask for legal research or document preparation...').fill(prompt);
  await page.getByRole('button', { name: 'Send message' }).click();
}

async function attachScreenshot(page: Page, testInfo: TestInfo, fileName: string) {
  const screenshotPath = testInfo.outputPath(fileName);
  await page.screenshot({ path: screenshotPath, fullPage: true });
  await testInfo.attach(fileName.replace(/\.png$/i, ''), {
    path: screenshotPath,
    contentType: 'image/png',
  });
}

test('admin can select Local Ollama qwen3:4b for assistant document drafting', async ({
  page,
}, testInfo) => {
  test.skip(!frontendBaseURL, 'Set FRONTEND_BASE_URL to run frontend assistant checks.');

  let promptSent = false;

  await page.setViewportSize({ width: 1440, height: 1100 });
  await seedSessionUser(page, {
    userId,
    email: userEmail,
    name: 'Admin Local Model E2E',
    role: 'Admin',
  });
  await page.route('**/v1/model-routing/effective**', async (route) => {
    await fulfillJson(route, {
      plan_code: 'free',
      route_type: 'free_local',
      provider: 'local_ollama',
      provider_display_name: 'Local Ollama',
      model: 'qwen3:1.7b',
      model_profile_id: 'local_ollama_default',
      is_local: true,
      is_external: false,
      label: defaultModelLabel,
    });
  });
  await page.route('**/v1/model-routing/selectable**', async (route) => {
    await fulfillJson(route, {
      eligible: true,
      profiles: [
        {
          model_profile_id: 'local_ollama_default',
          provider: 'local_ollama',
          provider_display_name: 'Local Ollama',
          model: 'qwen3:1.7b',
          label: defaultModelLabel,
          is_local: true,
          is_external: false,
          eu_data_zone_capable: true,
          context_window_tokens: 8192,
        },
        {
          model_profile_id: selectedModelProfileId,
          provider: 'local_ollama',
          provider_display_name: 'Local Ollama',
          model: 'qwen3:4b',
          label: selectedModelLabel,
          is_local: true,
          is_external: false,
          eu_data_zone_capable: true,
          context_window_tokens: 32768,
        },
      ],
    });
  });
  await page.route('**/v1/cases?**', async (route) => {
    await fulfillJson(route, [
      {
        case_id: caseId,
        user_id: userId,
        company_id: null,
        title: 'Admin local model selection case',
        status: 'open',
        created_at: now,
        updated_at: now,
      },
    ]);
  });
  await page.route(`**/v1/cases/${caseId}/history?**`, async (route) => {
    await fulfillJson(route, {
      messages: completedMessages(promptSent),
      documents: [],
      citations: [],
      has_more: false,
    });
  });
  await page.route('**/v1/chat/sessions', async (route) => {
    expect(route.request().method()).toBe('POST');
    const body = route.request().postDataJSON() as {
      user_id?: string | null;
      case_id?: string | null;
      model_profile_id?: string | null;
      language?: string | null;
    };
    expect(body.user_id).toBe(userId);
    expect(body.case_id).toBe(caseId);
    expect(body.model_profile_id).toBe(selectedModelProfileId);
    expect(body.language?.toLowerCase()).toContain('en');
    await fulfillJson(route, {
      id: sessionId,
      user_id: userId,
      case_id: caseId,
      country: 'SK',
      language: 'en',
      discussion_type: 'advice',
      state: 'active',
      created_at: now,
    });
  });
  await page.route(`**/v1/chat/sessions/${sessionId}/stream`, async (route) => {
    const body = route.request().postDataJSON() as {
      instruction?: string;
      user_simulation_mode?: string;
      user_id?: string | null;
      user_email?: string | null;
      model_profile_id?: string | null;
    };
    expect(body.instruction).toBe(draftingPrompt);
    expect(body.user_simulation_mode).toBe('ReadUser');
    expect(body.user_id).toBe(userId);
    expect(body.user_email).toBe(userEmail);
    expect(body.model_profile_id).toBe(selectedModelProfileId);
    promptSent = true;
    const streamBody = [
      'event: processing',
      `data: ${JSON.stringify({
        stage: 'thinking',
        message: `Drafting with selected assistant model ${selectedModelLabel}.`,
      })}`,
      '',
      'event: message',
      `data: ${JSON.stringify({ role: 'assistant', content: draftingAnswer, agent_name: 'LawyerSlovakia' })}`,
      '',
      'event: done',
      'data: {"status":"completed"}',
      '',
    ].join('\n');
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: streamBody,
    });
  });

  await page.goto(`${frontendBaseURL}/app/assistant`);
  await page.getByText('Admin local model selection case').click();

  const selector = page.getByRole('combobox', { name: 'Select assistant model' });
  await expect(selector).toBeVisible();
  await expect(selector).toContainText(defaultModelLabel);
  await selector.selectOption(selectedModelProfileId);
  await expect(selector).toHaveValue(selectedModelProfileId);

  await askAssistant(page, draftingPrompt);
  await expect(page.locator('.assistant-main')).toContainText(
    'Splnomocnenie je pripravene na zaklade vybraneho lokalneho modelu Local Ollama - qwen3:4b.',
  );
  await expect(page.locator('.assistant-main')).toContainText('ESolutions SK s.r.o.');
  await expect(page.locator('.assistant-main')).toContainText(draftingPrompt);

  await attachScreenshot(page, testInfo, 'frontend-admin-local-model-selection.png');
});

test('regular user stays on the default Local Ollama model without a selector', async ({
  page,
}, testInfo) => {
  test.skip(!frontendBaseURL, 'Set FRONTEND_BASE_URL to run frontend assistant checks.');

  const regularUserId = 'regular-local-model-e2e-user';
  const regularCaseId = 'regular-local-model-case';
  const regularSessionId = '55555555-5555-4555-8555-555555555555';
  const regularPrompt = 'Prepare a short legal note about a rental-deposit dispute.';
  const regularAnswer = [
    'This answer uses the default local route Local Ollama - qwen3:1.7b.',
    'Summary: review the deposit clause and request a written settlement timeline.',
  ].join('\n');
  let promptSent = false;

  await page.setViewportSize({ width: 1440, height: 1100 });
  await seedSessionUser(page, {
    userId: regularUserId,
    email: 'regular-local-model@example.test',
    name: 'Regular Local Model E2E',
    role: 'JurisDigta user',
  });
  await page.route('**/v1/model-routing/effective**', async (route) => {
    await fulfillJson(route, {
      plan_code: 'free',
      route_type: 'free_local',
      provider: 'local_ollama',
      provider_display_name: 'Local Ollama',
      model: 'qwen3:1.7b',
      model_profile_id: 'local_ollama_default',
      is_local: true,
      is_external: false,
      label: defaultModelLabel,
    });
  });
  await page.route('**/v1/model-routing/selectable**', async (route) => {
    const url = new URL(route.request().url());
    expect(url.searchParams.get('user_id')).toBe(regularUserId);
    expect(url.searchParams.get('user_email')).toBe('regular-local-model@example.test');
    await fulfillJson(route, { eligible: false, profiles: [] });
  });
  await page.route('**/v1/cases?**', async (route) => {
    await fulfillJson(route, [
      {
        case_id: regularCaseId,
        user_id: regularUserId,
        company_id: null,
        title: 'Regular default local model case',
        status: 'open',
        created_at: now,
        updated_at: now,
      },
    ]);
  });
  await page.route(`**/v1/cases/${regularCaseId}/history?**`, async (route) => {
    await fulfillJson(route, {
      messages: promptSent
        ? [
            {
              communication_id: 'regular-local-model-user-message',
              role: 'user',
              content: regularPrompt,
              agent_name: null,
              created_at: now,
              citations: [],
            },
            {
              communication_id: 'regular-local-model-assistant-message',
              role: 'assistant',
              content: regularAnswer,
              agent_name: 'LawyerSlovakia',
              created_at: now,
              citations: [],
            },
          ]
        : [],
      documents: [],
      citations: [],
      has_more: false,
    });
  });
  await page.route('**/v1/chat/sessions', async (route) => {
    const body = route.request().postDataJSON() as {
      user_id?: string | null;
      case_id?: string | null;
      model_profile_id?: string | null;
    };
    expect(body.user_id).toBe(regularUserId);
    expect(body.case_id).toBe(regularCaseId);
    expect(body.model_profile_id).toBeNull();
    await fulfillJson(route, {
      id: regularSessionId,
      user_id: regularUserId,
      case_id: regularCaseId,
      country: 'SK',
      language: 'en',
      discussion_type: 'advice',
      state: 'active',
      created_at: now,
    });
  });
  await page.route(`**/v1/chat/sessions/${regularSessionId}/stream`, async (route) => {
    const body = route.request().postDataJSON() as {
      instruction?: string;
      user_id?: string | null;
      user_email?: string | null;
      model_profile_id?: string | null;
    };
    expect(body.instruction).toBe(regularPrompt);
    expect(body.user_id).toBe(regularUserId);
    expect(body.user_email).toBe('regular-local-model@example.test');
    expect(body.model_profile_id).toBeNull();
    promptSent = true;
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        'event: processing',
        `data: ${JSON.stringify({
          stage: 'thinking',
          message: `Drafting with default assistant model ${defaultModelLabel}.`,
        })}`,
        '',
        'event: message',
        `data: ${JSON.stringify({ role: 'assistant', content: regularAnswer, agent_name: 'LawyerSlovakia' })}`,
        '',
        'event: done',
        'data: {"status":"completed"}',
        '',
      ].join('\n'),
    });
  });

  await page.goto(`${frontendBaseURL}/app/assistant`);
  await page.getByText('Regular default local model case').click();

  await expect(page.getByRole('combobox', { name: 'Select assistant model' })).toHaveCount(0);
  await expect(page.getByLabel('AI model used for this chat')).toContainText(defaultModelLabel);

  await askAssistant(page, regularPrompt);
  await expect(page.locator('.assistant-main')).toContainText(
    'This answer uses the default local route Local Ollama - qwen3:1.7b.',
  );

  await attachScreenshot(page, testInfo, 'frontend-regular-default-model.png');
});

test('admin sees both Local Ollama model options in the selector before drafting', async ({
  page,
}, testInfo) => {
  test.skip(!frontendBaseURL, 'Set FRONTEND_BASE_URL to run frontend assistant checks.');

  await page.setViewportSize({ width: 1440, height: 1100 });
  await seedSessionUser(page, {
    userId,
    email: userEmail,
    name: 'Admin Local Model E2E',
    role: 'Admin',
  });
  await page.route('**/v1/model-routing/effective**', async (route) => {
    await fulfillJson(route, {
      plan_code: 'free',
      route_type: 'free_local',
      provider: 'local_ollama',
      provider_display_name: 'Local Ollama',
      model: 'qwen3:1.7b',
      model_profile_id: 'local_ollama_default',
      is_local: true,
      is_external: false,
      label: defaultModelLabel,
    });
  });
  await page.route('**/v1/model-routing/selectable**', async (route) => {
    const url = new URL(route.request().url());
    expect(url.searchParams.get('user_id')).toBe(userId);
    expect(url.searchParams.get('user_email')).toBe(userEmail);
    await fulfillJson(route, {
      eligible: true,
      profiles: [
        {
          model_profile_id: 'local_ollama_default',
          provider: 'local_ollama',
          provider_display_name: 'Local Ollama',
          model: 'qwen3:1.7b',
          label: defaultModelLabel,
          is_local: true,
          is_external: false,
          eu_data_zone_capable: true,
          context_window_tokens: 8192,
        },
        {
          model_profile_id: selectedModelProfileId,
          provider: 'local_ollama',
          provider_display_name: 'Local Ollama',
          model: 'qwen3:4b',
          label: selectedModelLabel,
          is_local: true,
          is_external: false,
          eu_data_zone_capable: true,
          context_window_tokens: 32768,
        },
      ],
    });
  });
  await page.route('**/v1/cases?**', async (route) => {
    await fulfillJson(route, [
      {
        case_id: caseId,
        user_id: userId,
        company_id: null,
        title: 'Admin local model selection case',
        status: 'open',
        created_at: now,
        updated_at: now,
      },
    ]);
  });

  await page.goto(`${frontendBaseURL}/app/assistant`);
  await page.getByText('Admin local model selection case').click();

  const selector = page.getByRole('combobox', { name: 'Select assistant model' });
  await expect(selector).toBeVisible();
  await expect(selector).toContainText(defaultModelLabel);
  await expect(selector).toContainText(selectedModelLabel);

  await attachScreenshot(page, testInfo, 'frontend-admin-model-selector-options.png');
});
