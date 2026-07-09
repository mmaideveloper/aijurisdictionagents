import { expect, test, type Page, type Route, type TestInfo } from '@playwright/test';

const frontendBaseURL = process.env.FRONTEND_BASE_URL;
const authSessionKey = 'jurisdigta.web.auth.user.v1';
const userId = 'mcp-legal-query-e2e-user';
const caseId = 'mcp-legal-query-case';
const sessionId = '22222222-2222-4222-8222-222222222222';
const now = '2026-07-09T08:00:00.000Z';

const courtDecisionPrompt = 'Daj mi posledne sudne rozhodnutie ohladom podnajmu ?';
const rentalLawPrompt = 'Daj mi najnovsie zakony ktore sa tykaju prenajmu bytu?';

type ApiCitation = {
  id: string;
  case_id: string;
  question_message_id: string;
  answer_message_id: string;
  source_type: string;
  source_id: string;
  source_url: string | null;
  title: string;
  citation_label: string;
  law_number: string | null;
  section: string | null;
  effective_from: string | null;
  court: string | null;
  ecli: string | null;
  file_number: string | null;
  decision_date: string | null;
  snippet: string | null;
  retrieval_tool: string;
  relevance_score: number;
  created_at: string;
};

type ConversationResult = {
  prompt: string;
  answer: string;
  processingMessage: string;
  citations: ApiCitation[];
};

const latestSubleaseDecision: ApiCitation = {
  id: 'citation-decision-podnajom-latest',
  case_id: caseId,
  question_message_id: 'msg-user-court',
  answer_message_id: 'msg-assistant-court',
  source_type: 'court_decision',
  source_id: 'decision-podnajom-2026',
  source_url: 'https://obcan.justice.sk/infosud/-/detail/decision-podnajom-2026',
  title: 'Krajsky sud Bratislava - 8Co/44/2026 - podnajom bytu',
  citation_label: 'Krajsky sud Bratislava - 8Co/44/2026 - podnajom bytu',
  law_number: null,
  section: null,
  effective_from: null,
  court: 'Krajsky sud Bratislava',
  ecli: 'ECLI:SK:KSBA:2026:8CO44.1',
  file_number: '8Co/44/2026',
  decision_date: '2026-05-18',
  snippet: 'Najnovsie pseudonymizovane rozhodnutie k podnajmu bytu a suhlasu prenajimatela.',
  retrieval_tool: 'JurisDigta MCP searchLegalSources',
  relevance_score: 0.99,
  created_at: now,
};

const rentalLawCitations: ApiCitation[] = [
  {
    id: 'citation-law-40-1964-rental',
    case_id: caseId,
    question_message_id: 'msg-user-laws',
    answer_message_id: 'msg-assistant-laws',
    source_type: 'law',
    source_id: 'law-40-1964',
    source_url: 'https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/1964/40/',
    title: 'Obciansky zakonnik - najom a podnajom bytu',
    citation_label: '40/1964 Zb. Obciansky zakonnik',
    law_number: '40/1964 Zb.',
    section: '§ 685',
    effective_from: '2026-01-01',
    court: null,
    ecli: null,
    file_number: null,
    decision_date: null,
    snippet: 'Najom bytu a zakladne prava a povinnosti najomcu a prenajimatela.',
    retrieval_tool: 'JurisDigta MCP searchLaws',
    relevance_score: 0.98,
    created_at: now,
  },
  {
    id: 'citation-law-98-2014-rental',
    case_id: caseId,
    question_message_id: 'msg-user-laws',
    answer_message_id: 'msg-assistant-laws',
    source_type: 'law',
    source_id: 'law-98-2014',
    source_url: 'https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/2014/98/',
    title: 'Zakon o kratkodobom najme bytu',
    citation_label: '98/2014 Z. z. Zakon o kratkodobom najme bytu',
    law_number: '98/2014 Z. z.',
    section: '§ 3',
    effective_from: '2026-02-01',
    court: null,
    ecli: null,
    file_number: null,
    decision_date: null,
    snippet: 'Najnovsia relevantna uprava kratkodobeho najmu bytu.',
    retrieval_tool: 'JurisDigta MCP searchLaws',
    relevance_score: 0.97,
    created_at: now,
  },
];

const results: Record<string, ConversationResult> = {
  [courtDecisionPrompt]: {
    prompt: courtDecisionPrompt,
    processingMessage: 'JurisDigta MCP Server na ziadosti pracuje, zvoleny tool: searchLegalSources.',
    answer: [
      'Najnovsie sudne rozhodnutie k podnajmu:',
      'Krajsky sud Bratislava - 8Co/44/2026 - podnajom bytu.',
      'Rozhodnutie riesi podnajom bytu a potrebu suhlasu prenajimatela.',
    ].join('\n'),
    citations: [latestSubleaseDecision],
  },
  [rentalLawPrompt]: {
    prompt: rentalLawPrompt,
    processingMessage: 'JurisDigta MCP Server na ziadosti pracuje, zvoleny tool: searchLaws, getLawText.',
    answer: [
      'Najnovsie zakony k prenajmu bytu:',
      '1. 40/1964 Zb. Obciansky zakonnik - najom a podnajom bytu.',
      '2. 98/2014 Z. z. Zakon o kratkodobom najme bytu.',
    ].join('\n'),
    citations: rentalLawCitations,
  },
};

async function authenticate(page: Page) {
  await page.addInitScript(
    ({ key }) => {
      window.localStorage.setItem('aj_frontend_lang', 'sk');
      window.sessionStorage.setItem(
        key,
        JSON.stringify({
          userId: 'mcp-legal-query-e2e-user',
          email: 'mcp-legal-query@example.test',
          name: 'MCP Legal Query E2E User',
          role: 'JurisDigta user',
        }),
      );
    },
    { key: authSessionKey },
  );
}

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

function completedMessages(completedPrompts: string[]) {
  return completedPrompts.flatMap((prompt, index) => {
    const result = results[prompt];
    return [
      {
        communication_id: index === 0 ? 'msg-user-court' : 'msg-user-laws',
        role: 'user',
        content: prompt,
        agent_name: null,
        created_at: now,
        citations: [],
      },
      {
        communication_id: index === 0 ? 'msg-assistant-court' : 'msg-assistant-laws',
        role: 'assistant',
        content: result.answer,
        agent_name: 'LawyerSlovakia',
        created_at: now,
        citations: result.citations,
      },
    ];
  });
}

function completedCitations(completedPrompts: string[]) {
  return completedPrompts.flatMap((prompt) => results[prompt].citations);
}

async function askAssistant(page: Page, prompt: string) {
  await page.locator('.assistant-composer__input').fill(prompt);
  await page.getByRole('button', { name: 'Odoslať správu' }).click();
}

async function attachScreenshot(page: Page, testInfo: TestInfo) {
  const screenshotPath = testInfo.outputPath('mcp-legal-query-answers.png');
  await page.screenshot({ path: screenshotPath, fullPage: true });
  await testInfo.attach('mcp-legal-query-answers', {
    path: screenshotPath,
    contentType: 'image/png',
  });
}

test('assistant answers latest sublease court decision and newest apartment-rental laws through MCP', async ({
  page,
}, testInfo) => {
  test.skip(!frontendBaseURL, 'Set FRONTEND_BASE_URL to run frontend assistant checks.');

  const completedPrompts: string[] = [];
  const streamedPrompts: string[] = [];

  await page.setViewportSize({ width: 1440, height: 1100 });
  await authenticate(page);
  await page.route('**/v1/model-routing/effective**', async (route) => {
    await fulfillJson(route, { provider: 'azurefoundry', model: 'gpt-4o-mini', route_type: 'paid_case' });
  });
  await page.route('**/v1/cases?**', async (route) => {
    await fulfillJson(route, [
      {
        case_id: caseId,
        user_id: userId,
        company_id: null,
        title: 'MCP legal query answer case',
        status: 'open',
        created_at: now,
        updated_at: now,
      },
    ]);
  });
  await page.route(`**/v1/cases/${caseId}/history?**`, async (route) => {
    await fulfillJson(route, {
      messages: completedMessages(completedPrompts),
      documents: [],
      citations: completedCitations(completedPrompts),
      has_more: false,
    });
  });
  await page.route('**/v1/chat/sessions', async (route) => {
    expect(route.request().method()).toBe('POST');
    await fulfillJson(route, {
      id: sessionId,
      user_id: userId,
      case_id: caseId,
      country: 'SK',
      language: 'sk-SK',
      discussion_type: 'advice',
      state: 'active',
      created_at: now,
    });
  });
  await page.route(`**/v1/chat/sessions/${sessionId}/stream`, async (route) => {
    const body = route.request().postDataJSON() as { instruction?: string; user_simulation_mode?: string };
    const prompt = body.instruction ?? '';
    const result = results[prompt];
    expect(result, `Unexpected prompt: ${prompt}`).toBeDefined();
    expect(body.user_simulation_mode).toBe('ReadUser');
    streamedPrompts.push(prompt);
    completedPrompts.push(prompt);
    const streamBody = [
      'event: processing',
      `data: ${JSON.stringify({ stage: 'mcp_law_context', message: result.processingMessage })}`,
      '',
      'event: message',
      `data: ${JSON.stringify({ role: 'assistant', content: result.answer, agent_name: 'LawyerSlovakia' })}`,
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
  await page.getByText('MCP legal query answer case').click();

  await askAssistant(page, courtDecisionPrompt);
  await expect(page.getByText('Najnovsie sudne rozhodnutie k podnajmu')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText('Krajsky sud Bratislava - 8Co/44/2026 - podnajom bytu').first()).toBeVisible();

  await askAssistant(page, rentalLawPrompt);
  await expect(page.getByText('Najnovsie zakony k prenajmu bytu')).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('.assistant-main')).toContainText('40/1964 Zb. Obciansky zakonnik');
  await expect(page.locator('.assistant-main')).toContainText('98/2014 Z. z. Zakon o kratkodobom najme bytu');

  await expect(page.locator('.assistant-main')).toContainText(courtDecisionPrompt);
  await expect(page.locator('.assistant-main')).toContainText(rentalLawPrompt);
  await expect(page.locator('.assistant-tool-panel')).toContainText('JurisDigta MCP searchLegalSources');
  await expect(page.locator('.assistant-tool-panel')).toContainText('JurisDigta MCP searchLaws');
  await expect(page.locator('.assistant-tool-panel')).toContainText('8Co/44/2026');
  await expect(page.locator('.assistant-tool-panel')).toContainText('40/1964 Zb.');
  await expect(page.locator('.assistant-tool-panel')).toContainText('98/2014 Z. z.');
  expect(streamedPrompts).toEqual([courtDecisionPrompt, rentalLawPrompt]);

  await attachScreenshot(page, testInfo);
});
