import { expect, test, type Page, type Route } from '@playwright/test';

const frontendBaseURL = process.env.FRONTEND_BASE_URL;
const authSessionKey = 'jurisdigta.web.auth.user.v1';
const prompt = 'Daj mi top 5 sudnych rozhodnuti ohladom podnajmu?';
const userId = 'legal-rag-e2e-user';
const caseId = 'legal-rag-case';
const now = '2026-07-07T07:00:00.000Z';

const decisionCitations = Array.from({ length: 5 }, (_, index) => {
  const number = index + 1;
  const year = 2020 + number;
  return {
    id: `citation-decision-${number}`,
    case_id: caseId,
    question_message_id: 'msg-user-1',
    answer_message_id: 'msg-assistant-1',
    source_type: 'court_decision',
    source_id: `decision-${number}`,
    source_url: `https://obcan.justice.sk/infosud/-/detail/decision-${number}`,
    title: `Najvyssi sud SR - ${number}Cdo/${year} - ${year}`,
    citation_label: `Najvyssi sud SR - ${number}Cdo/${year} - ${year}`,
    law_number: null,
    section: null,
    effective_from: null,
    court: 'Najvyssi sud SR',
    ecli: null,
    file_number: `${number}Cdo/${year}`,
    decision_date: `${year}-03-01`,
    snippet: `Pseudonymizovany verejny metadatovy vysledok k podnajmu ${number}.`,
    retrieval_tool: 'JurisDigta MCP searchCourtDecisions',
    relevance_score: 0.99 - index / 100,
    created_at: now,
  };
});

const webFallbackCitation = {
  id: 'citation-web-fallback',
  case_id: caseId,
  question_message_id: 'msg-user-1',
  answer_message_id: 'msg-assistant-1',
  source_type: 'web',
  source_id: 'https://obcan.justice.sk/infosud/-/detail/fallback',
  source_url: 'https://obcan.justice.sk/infosud/-/detail/fallback',
  title: 'Fallback rozhodnutie z oficialneho webu',
  citation_label: 'Fallback rozhodnutie z oficialneho webu',
  law_number: null,
  section: null,
  effective_from: null,
  court: null,
  ecli: null,
  file_number: null,
  decision_date: '2026-01-15',
  snippet: 'Official web fallback citation.',
  retrieval_tool: 'AIWebSearchAgent official web fallback',
  relevance_score: 0.9,
  created_at: now,
};

const assistantAnswer = [
  'Nasiel som 5 sudnych rozhodnuti k podnajmu cez JurisDigta MCP:',
  ...decisionCitations.map((citation, index) => `${index + 1}. ${citation.title}`),
].join('\n');

async function authenticate(page: Page) {
  await page.addInitScript(
    ({ key }) => {
      window.localStorage.setItem('aj_frontend_lang', 'en');
      window.sessionStorage.setItem(
        key,
        JSON.stringify({
          userId: 'legal-rag-e2e-user',
          email: 'legal-rag@example.test',
          name: 'Legal RAG E2E User',
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

test('assistant asks MCP for top five court decisions and renders provenance', async ({ page }) => {
  test.skip(!frontendBaseURL, 'Set FRONTEND_BASE_URL to run frontend assistant checks.');

  let streamedPrompt = '';
  let streamCompleted = false;

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
        title: 'Legal RAG court-decision case',
        status: 'open',
        created_at: now,
        updated_at: now,
      },
    ]);
  });
  await page.route(`**/v1/cases/${caseId}/history?**`, async (route) => {
    await fulfillJson(route, {
      messages: streamCompleted
        ? [
            {
              communication_id: 'msg-user-1',
              role: 'user',
              content: prompt,
              agent_name: null,
              created_at: now,
              citations: [],
            },
            {
              communication_id: 'msg-assistant-1',
              role: 'assistant',
              content: assistantAnswer,
              agent_name: 'LawyerSlovakia',
              created_at: now,
              citations: decisionCitations,
            },
          ]
        : [],
      documents: [],
      citations: streamCompleted ? [...decisionCitations, webFallbackCitation] : [],
      has_more: false,
    });
  });
  await page.route('**/v1/chat/sessions', async (route) => {
    expect(route.request().method()).toBe('POST');
    await fulfillJson(route, {
      id: '11111111-1111-4111-8111-111111111111',
      user_id: userId,
      case_id: caseId,
      country: 'SK',
      language: 'en',
      discussion_type: 'advice',
      state: 'active',
      created_at: now,
    });
  });
  await page.route('**/v1/chat/sessions/11111111-1111-4111-8111-111111111111/stream', async (route) => {
    const body = route.request().postDataJSON() as { instruction?: string; user_simulation_mode?: string };
    streamedPrompt = body.instruction ?? '';
    expect(body.user_simulation_mode).toBe('ReadUser');
    streamCompleted = true;
    const streamBody = [
      'event: processing',
      'data: {"stage":"mcp_law_context","message":"JurisDigta MCP searched laws and court decisions for this legal turn.","details":{"tool_calls":["searchLegalSources"],"court_decision_count":5,"source_origin":"system_vector_db"}}',
      '',
      'event: message',
      `data: ${JSON.stringify({ role: 'assistant', content: assistantAnswer, agent_name: 'LawyerSlovakia' })}`,
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
  await page.getByText('Legal RAG court-decision case').click();
  await page.locator('.assistant-composer__input').fill(prompt);
  await page.getByRole('button', { name: 'Send' }).click();

  await expect(page.getByText('Nasiel som 5 sudnych rozhodnuti')).toBeVisible({ timeout: 20_000 });
  for (const citation of decisionCitations) {
    await expect(page.locator('.assistant-main').getByText(citation.title).first()).toBeVisible();
  }
  await expect(page.locator('.assistant-tool-panel').getByText('JurisDigta MCP searchCourtDecisions')).toHaveCount(5);
  await expect(page.locator('.assistant-tool-panel').getByText('Fallback rozhodnutie z oficialneho webu')).toBeVisible();
  await expect(page.getByText('official web-search fallback, not from JurisDigta system vector DB')).toBeVisible();
  expect(streamedPrompt).toBe(prompt);
  expect(streamCompleted).toBe(true);
});
