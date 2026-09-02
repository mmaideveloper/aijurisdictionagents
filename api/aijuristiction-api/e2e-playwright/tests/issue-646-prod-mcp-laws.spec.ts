import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { createHash, randomBytes, randomUUID } from 'crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

type Scenario = {
  schemaVersion: number;
  scenarioId: string;
  countryCode: string;
  law: {
    number: number;
    year: number;
    identifier: string;
    question: string;
  };
  modelMatrix: ModelCell[];
};

type ModelCell = {
  id: string;
  email: string;
  expectedPlan: string;
  expectedProvider: string;
  expectedModel: string;
  expectedModelProfileId: string;
};

type McpSource = {
  documentId: string;
  identifier: string;
  title: string;
  sourceUrl: string;
  textCharacters: number;
  summary?: string;
};

type CaseCitation = {
  source_type?: string | null;
  source_id?: string | null;
  source_url?: string | null;
  title?: string | null;
  citation_label?: string | null;
  law_number?: string | null;
  retrieval_tool?: string | null;
};

type ModelAuditEntry = {
  provider?: string | null;
  model?: string | null;
  route_type?: string | null;
  fallback_reason?: string | null;
  latency_ms?: number | null;
  status?: string | null;
};

type MatrixResult = {
  id: string;
  status: 'passed' | 'failed';
  expectedRoute: { plan: string; provider: string; model: string };
  actualRoute?: { plan: string; provider: string; model: string; modelProfileId: string; routeType: string };
  directMcp?: McpSource;
  observedCitation?: {
    sourceId: string;
    sourceUrl: string;
    lawNumber: string;
    retrievalTool: string;
  };
  aiWebSearchAgentUsed?: boolean;
  answerSha256?: string;
  answerPreview?: string;
  modelAudit?: ModelAuditEntry;
  screenshot?: string;
  error?: string;
};

const scenario = JSON.parse(
  readFileSync(join(process.cwd(), 'tests', 'fixtures', 'issue-646-prod-mcp-laws.json'), 'utf8'),
) as Scenario;
const apiBaseUrl = (process.env.API_BASE_URL ?? 'https://api.jurisdigta.eu').replace(/\/$/, '');
const frontendBaseUrl = (process.env.FRONTEND_BASE_URL ?? 'https://web.jurisdigta.eu').replace(/\/$/, '');
const mcpBaseUrl = (process.env.MCP_PUBLIC_BASE_URL ?? 'https://mcp.jurisdigta.eu').replace(/\/$/, '');
const apiKey = process.env.API_KEY?.trim() || 'aijuris';
const e2ePassword = process.env.JURISDIGTA_E2E_TEST_USER_PASSWORD?.trim() || '';
const expectedCommitSha = process.env.ISSUE_646_DEPLOYED_COMMIT_SHA?.trim() || '';
const timeoutMs = Number(process.env.ISSUE_646_TIMEOUT_MS ?? 660_000);
const authSessionKey = 'jurisdigta.web.auth.user.v1';

test.describe.configure({ mode: 'serial' });

test('production MCP law grounding is preserved through Azure Foundry gpt-5-mini', async ({
  browser,
  request,
}, testInfo) => {
  test.setTimeout(timeoutMs * scenario.modelMatrix.length + 180_000);
  expect(e2ePassword, 'JURISDIGTA_E2E_TEST_USER_PASSWORD must be supplied securely').not.toBe('');
  expect(e2ePassword).not.toBe('unknown-variable');
  expect(expectedCommitSha, 'ISSUE_646_DEPLOYED_COMMIT_SHA is required for deployment traceability').toMatch(
    /^[0-9a-f]{40}$/i,
  );

  const versionResponse = await request.get(`${apiBaseUrl}/version`, { headers: apiHeaders() });
  expect(versionResponse.ok()).toBeTruthy();
  const version = (await versionResponse.json()) as Record<string, unknown>;
  const runId = `issue-646-${new Date().toISOString().replace(/[:.]/g, '-')}-${randomUUID().slice(0, 8)}`;
  const matrixResults: MatrixResult[] = [];

  for (const cell of scenario.modelMatrix) {
    const result: MatrixResult = {
      id: cell.id,
      status: 'failed',
      expectedRoute: {
        plan: cell.expectedPlan,
        provider: cell.expectedProvider,
        model: cell.expectedModel,
      },
    };
    const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } });
    let userId = '';
    let caseId = '';

    try {
      const oauth = await authorizeMcp(request, cell.email, e2ePassword);
      userId = oauth.userId;
      const directMcp = await discoverLawThroughMcp(request, oauth.accessToken);
      result.directMcp = directMcp;

      const routeResponse = await request.get(
        `${apiBaseUrl}/v1/model-routing/effective?task_type=chat_reply&user_id=${encodeURIComponent(userId)}`,
        { headers: apiHeaders() },
      );
      expect(routeResponse.ok()).toBeTruthy();
      const route = (await routeResponse.json()) as Record<string, unknown>;
      result.actualRoute = {
        plan: String(route.plan_code ?? ''),
        provider: String(route.provider ?? ''),
        model: String(route.model ?? ''),
        modelProfileId: String(route.model_profile_id ?? ''),
        routeType: String(route.route_type ?? ''),
      };
      expect(result.actualRoute.plan).toBe(cell.expectedPlan);
      expect(normalizeProvider(result.actualRoute.provider)).toBe(normalizeProvider(cell.expectedProvider));
      expect(normalizeModel(result.actualRoute.model)).toBe(normalizeModel(cell.expectedModel));
      expect(result.actualRoute.modelProfileId).toBe(cell.expectedModelProfileId);
      expect(result.actualRoute.routeType).not.toMatch(/fallback/i);

      await removePriorSyntheticCases(request, userId);
      const caseTitle = `[${runId}] MCP laws ${cell.id}`;
      const caseResponse = await request.post(`${apiBaseUrl}/v1/cases`, {
        headers: apiHeaders(),
        data: { user_id: userId, title: caseTitle },
      });
      expect(caseResponse.status()).toBe(201);
      const createdCase = (await caseResponse.json()) as Record<string, unknown>;
      caseId = String(createdCase.case_id ?? '');
      expect(caseId).not.toBe('');

      await waitForSyntheticCasePersistence(request, userId, caseId, caseTitle);
      await seedFrontendSession(page, userId, cell.email);
      await openSyntheticCaseInFrontend(page, caseId, caseTitle);
      await expect(page.locator('.assistant-model-disclosure')).toContainText(
        new RegExp(escapeRegex(cell.expectedModel), 'i'),
        { timeout: 60_000 },
      );
      await page.locator('.assistant-composer__input').fill(scenario.law.question);
      await page.locator('.assistant-composer__send').click();
      const completedAssistantMessage = page.locator('.assistant-message').last();
      await expect(completedAssistantMessage).toContainText(scenario.law.identifier, {
        timeout: timeoutMs,
      });
      await expect(page.locator('.assistant-tool-panel')).toContainText(/JurisDigta MCP/i, {
        timeout: timeoutMs,
      });

      const historyResponse = await request.get(
        `${apiBaseUrl}/v1/cases/${encodeURIComponent(caseId)}/history?user_id=${encodeURIComponent(userId)}&limit=20`,
        { headers: apiHeaders() },
      );
      expect(historyResponse.ok()).toBeTruthy();
      const history = (await historyResponse.json()) as {
        messages?: Array<{ role?: string; content?: string }>;
        citations?: CaseCitation[];
      };
      const assistantMessages = (history.messages ?? []).filter((message) => message.role === 'assistant');
      const answer = String(assistantMessages.at(-1)?.content ?? '').trim();
      expect(answer).toContain(scenario.law.identifier);
      const citations = history.citations ?? [];
      const mcpCitation = citations.find((citation) =>
        citationMatchesDirectMcp(citation, directMcp),
      );
      expect(mcpCitation, 'The persisted case citation must match the direct MCP source').toBeTruthy();
      expect(String(mcpCitation?.source_url ?? '')).toBe(directMcp.sourceUrl);
      expect(String(mcpCitation?.title ?? mcpCitation?.citation_label ?? '')).toContain(directMcp.title);
      const aiWebSearchAgentUsed = citations.some(
        (citation) =>
          String(citation.source_type ?? '').toLowerCase() === 'web' ||
          /AIWebSearchAgent/i.test(String(citation.retrieval_tool ?? '')),
      );
      expect(aiWebSearchAgentUsed, 'AIWebSearchAgent/web fallback must not satisfy this MCP test').toBe(false);
      expect(String(mcpCitation?.retrieval_tool ?? '')).toMatch(/JurisDigta MCP/i);

      const auditResponse = await request.get(
        `${apiBaseUrl}/v1/cases/${encodeURIComponent(caseId)}/ai-model-audit?user_id=${encodeURIComponent(userId)}&limit=20`,
        { headers: apiHeaders() },
      );
      expect(auditResponse.ok()).toBeTruthy();
      const audit = (await auditResponse.json()) as { entries?: ModelAuditEntry[] };
      const modelAudit = audit.entries?.[0];
      expect(normalizeProvider(String(modelAudit?.provider ?? ''))).toBe(normalizeProvider(cell.expectedProvider));
      expect(normalizeModel(String(modelAudit?.model ?? ''))).toBe(normalizeModel(cell.expectedModel));
      expect(String(modelAudit?.route_type ?? '')).not.toMatch(/fallback/i);

      result.observedCitation = {
        sourceId: String(mcpCitation?.source_id ?? ''),
        sourceUrl: String(mcpCitation?.source_url ?? ''),
        lawNumber: String(mcpCitation?.law_number ?? ''),
        retrievalTool: String(mcpCitation?.retrieval_tool ?? ''),
      };
      result.aiWebSearchAgentUsed = aiWebSearchAgentUsed;
      result.answerSha256 = sha256(answer);
      result.answerPreview = safePreview(answer);
      result.modelAudit = modelAudit;
      result.status = 'passed';
    } catch (error) {
      result.error = sanitizeError(error);
    } finally {
      const screenshotName = `issue-646-${cell.id}-${result.status}.png`;
      const screenshotPath = testInfo.outputPath(screenshotName);
      try {
        await page.screenshot({ path: screenshotPath, fullPage: true });
        result.screenshot = screenshotName;
      } catch {
        // The sanitized manifest still records the failure when navigation prevented a screenshot.
      }
      if (caseId && userId) {
        await request
          .delete(
            `${apiBaseUrl}/v1/cases/${encodeURIComponent(caseId)}?user_id=${encodeURIComponent(userId)}`,
            { headers: apiHeaders() },
          )
          .catch(() => undefined);
      }
      await page.close();
      matrixResults.push(result);
    }
  }

  const manifest = {
    schemaVersion: 1,
    scenarioId: scenario.scenarioId,
    runId,
    syntheticOnly: true,
    productionTarget: {
      deployedCommitSha: expectedCommitSha,
      apiBaseUrl,
      frontendBaseUrl,
      mcpBaseUrl,
      apiVersion: String(version.api_version ?? version.version ?? ''),
      mcpVersion: String(version.mcp_server_version ?? ''),
    },
    question: scenario.law.question,
    deterministicContract: {
      exactProseRequired: false,
      requiredLawIdentifier: scenario.law.identifier,
      requiredSameMcpDocumentId: true,
      aiWebSearchAgentAllowed: false,
    },
    knowledgeFreshness: {
      lawYear: scenario.law.year,
      modelKnowledgeCutoffDate: version.model_knowledge_cutoff_date ?? null,
      modelKnowledgeCutoffSource: version.model_knowledge_cutoff_source ?? 'unavailable',
      proofMode:
        version.model_knowledge_cutoff_date == null
          ? 'mcp-source-identity-and-no-web-fallback'
          : 'mcp-source-identity-plus-law-after-recorded-model-cutoff',
    },
    matrix: matrixResults,
    retention: 'Delete this ignored evidence within 7 days.',
  };
  const manifestPath = testInfo.outputPath('issue-646-result-manifest.json');
  writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
  await testInfo.attach('issue-646-result-manifest', {
    path: manifestPath,
    contentType: 'application/json',
  });
  for (const result of matrixResults) {
    if (result.screenshot) {
      await testInfo.attach(`issue-646-${result.id}`, {
        path: testInfo.outputPath(result.screenshot),
        contentType: 'image/png',
      });
    }
  }

  expect(
    matrixResults.filter((result) => result.status === 'failed').map((result) => ({
      id: result.id,
      error: result.error,
    })),
    'Every required real-model cell must pass; fallback or unavailable credentials are not acceptance',
  ).toEqual([]);
});

test('production remains stable when a synthetic case requests the latest five laws with summaries', async ({
  browser,
  request,
}, testInfo) => {
  test.setTimeout(timeoutMs + 180_000);
  expect(e2ePassword, 'JURISDIGTA_E2E_TEST_USER_PASSWORD must be supplied securely').not.toBe('');
  expect(expectedCommitSha).toMatch(/^[0-9a-f]{40}$/i);
  const cell = scenario.modelMatrix.find((item) => item.expectedPlan === 'paid') ?? scenario.modelMatrix[0];
  expect(cell).toBeTruthy();
  const requestedQuestion = 'Zobraz mi poslednych 5 novych zakonov aj so sumarom coho sa tykaju.&#x20;';
  const submittedQuestion = 'Zobraz mi poslednych 5 novych zakonov aj so sumarom coho sa tykaju. ';
  const runId = `issue-635-prod-stability-${new Date().toISOString().replace(/[:.]/g, '-')}-${randomUUID().slice(0, 8)}`;
  const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } });
  let userId = '';
  let caseId = '';
  let screenshotName = '';
  let manifest: Record<string, unknown> = {};
  try {
    const oauth = await authorizeMcp(request, cell!.email, e2ePassword);
    userId = oauth.userId;
    const latestSources = await discoverLatestLawsThroughMcp(request, oauth.accessToken, submittedQuestion);
    expect(latestSources).toHaveLength(5);

    const routeResponse = await request.get(
      `${apiBaseUrl}/v1/model-routing/effective?task_type=chat_reply&user_id=${encodeURIComponent(userId)}`,
      { headers: apiHeaders() },
    );
    expect(routeResponse.ok()).toBeTruthy();
    const route = (await routeResponse.json()) as Record<string, unknown>;
    expect(normalizeProvider(String(route.provider ?? ''))).toBe(normalizeProvider(cell!.expectedProvider));
    expect(normalizeModel(String(route.model ?? ''))).toBe(normalizeModel(cell!.expectedModel));
    expect(String(route.route_type ?? '')).not.toMatch(/fallback/i);

    const caseTitle = `[${runId}] Latest five laws`;
    const caseResponse = await request.post(`${apiBaseUrl}/v1/cases`, {
      headers: apiHeaders(),
      data: { user_id: userId, title: caseTitle },
    });
    expect(caseResponse.status()).toBe(201);
    caseId = String(((await caseResponse.json()) as Record<string, unknown>).case_id ?? '');
    expect(caseId).not.toBe('');

    await waitForSyntheticCasePersistence(request, userId, caseId, caseTitle);
    await seedFrontendSession(page, userId, cell!.email);
    await openSyntheticCaseInFrontend(page, caseId, caseTitle);
    await page.locator('.assistant-composer__input').fill(submittedQuestion);
    await page.locator('.assistant-composer__send').click();
    const assistantMessage = page.locator('.assistant-message').last();
    await expect(assistantMessage).toContainText(/zákon|zakon/i, { timeout: timeoutMs });
    await expect(page.locator('.assistant-tool-panel')).toContainText(/JurisDigta MCP/i, {
      timeout: timeoutMs,
    });

    const historyResponse = await request.get(
      `${apiBaseUrl}/v1/cases/${encodeURIComponent(caseId)}/history?user_id=${encodeURIComponent(userId)}&limit=20`,
      { headers: apiHeaders() },
    );
    expect(historyResponse.ok()).toBeTruthy();
    const history = (await historyResponse.json()) as {
      messages?: Array<{ role?: string; content?: string }>;
      citations?: CaseCitation[];
    };
    const answer = String(
      (history.messages ?? []).filter((message) => message.role === 'assistant').at(-1)?.content ?? '',
    );
    const citationIds = new Set((history.citations ?? []).map((citation) => String(citation.source_id ?? '')));
    const observed = latestSources.filter((source) => citationIds.has(source.documentId));
    expect(observed, 'All five latest MCP sources must persist as case citations').toHaveLength(5);
    for (const source of latestSources) {
      expect(answer, `Answer must identify ${source.identifier}`).toContain(source.identifier);
      expect(answer, `Answer must include the title for ${source.identifier}`).toContain(source.title);
      expect(source.summary, `MCP summary must exist for ${source.identifier}`).not.toBe('');
      expect(answer, `Answer must include the summary for ${source.identifier}`).toContain(String(source.summary));
    }

    const auditResponse = await request.get(
      `${apiBaseUrl}/v1/cases/${encodeURIComponent(caseId)}/ai-model-audit?user_id=${encodeURIComponent(userId)}&limit=20`,
      { headers: apiHeaders() },
    );
    expect(auditResponse.ok()).toBeTruthy();
    const audit = (await auditResponse.json()) as { entries?: ModelAuditEntry[] };
    const modelAudit = audit.entries?.[0];
    expect(normalizeProvider(String(modelAudit?.provider ?? ''))).toBe(normalizeProvider(cell!.expectedProvider));
    expect(normalizeModel(String(modelAudit?.model ?? ''))).toBe(normalizeModel(cell!.expectedModel));
    expect(String(modelAudit?.route_type ?? '')).not.toMatch(/fallback/i);

    screenshotName = 'issue-635-prod-stability-passed.png';
    await page.screenshot({ path: testInfo.outputPath(screenshotName), fullPage: true });
    manifest = {
      schemaVersion: 1,
      scenarioId: 'issue-635-prod-stability-latest-five-laws',
      runId,
      syntheticOnly: true,
      requestedQuestion,
      submittedNormalizedQuestion: submittedQuestion.trim(),
      deployedCommitSha: expectedCommitSha,
      services: { frontendBaseUrl, apiBaseUrl, mcpBaseUrl, database: 'production-postgresql' },
      realModelRoute: {
        provider: String(route.provider ?? ''),
        model: String(route.model ?? ''),
        modelProfileId: String(route.model_profile_id ?? ''),
        routeType: String(route.route_type ?? ''),
      },
      expectedSourceIds: latestSources.map((source) => source.documentId),
      observedSourceIds: observed.map((source) => source.documentId),
      answerSha256: sha256(answer),
      screenshot: screenshotName,
      retention: 'Delete this ignored evidence within 7 days.',
      result: 'passed',
    };
  } finally {
    if (!screenshotName) {
      screenshotName = 'issue-635-prod-stability-failed.png';
      await page.screenshot({ path: testInfo.outputPath(screenshotName), fullPage: true }).catch(() => undefined);
    }
    const manifestPath = testInfo.outputPath('issue-635-prod-stability-manifest.json');
    writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
    await testInfo.attach('issue-635-prod-stability-manifest', {
      path: manifestPath,
      contentType: 'application/json',
    });
    await testInfo.attach('issue-635-prod-stability-screenshot', {
      path: testInfo.outputPath(screenshotName),
      contentType: 'image/png',
    }).catch(() => undefined);
    if (caseId && userId) {
      await request.delete(
        `${apiBaseUrl}/v1/cases/${encodeURIComponent(caseId)}?user_id=${encodeURIComponent(userId)}`,
        { headers: apiHeaders() },
      ).catch(() => undefined);
    }
    await page.close();
  }
});

function apiHeaders(): Record<string, string> {
  return { 'x-api-key': apiKey, Accept: 'application/json' };
}

function normalizeModel(value: string): string {
  return value.trim().toLowerCase();
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

async function authorizeMcp(
  request: APIRequestContext,
  email: string,
  password: string,
): Promise<{ accessToken: string; userId: string }> {
  const redirectUri = 'http://127.0.0.1:47123/callback';
  const registrationResponse = await request.post(`${mcpBaseUrl}/oauth/register`, {
    data: {
      client_name: 'JurisDigta issue 646 post-deployment E2E',
      redirect_uris: [redirectUri],
      grant_types: ['authorization_code'],
      response_types: ['code'],
      token_endpoint_auth_method: 'none',
      scope: 'mcp:laws',
    },
  });
  expect(registrationResponse.status()).toBe(201);
  const registration = (await registrationResponse.json()) as { client_id?: string };
  const clientId = String(registration.client_id ?? '');
  expect(clientId).not.toBe('');

  const verifier = randomBytes(48).toString('base64url');
  const challenge = createHash('sha256').update(verifier, 'ascii').digest('base64url');
  const state = randomUUID();
  const resource = `${mcpBaseUrl}/MCP`;
  const loginResponse = await request.post(`${mcpBaseUrl}/oauth/authorize/login`, {
    form: {
      response_type: 'code',
      client_id: clientId,
      redirect_uri: redirectUri,
      code_challenge: challenge,
      code_challenge_method: 'S256',
      state,
      resource,
      scope: 'mcp:laws',
      email,
      password,
    },
    maxRedirects: 0,
  });
  expect(
    loginResponse.status(),
    'Controlled production MCP OAuth MFA bypass must be enabled only for the synthetic E2E users',
  ).toBe(303);
  const location = loginResponse.headers().location ?? '';
  const callback = new URL(location);
  expect(callback.searchParams.get('state')).toBe(state);
  const code = callback.searchParams.get('code') ?? '';
  expect(code).not.toBe('');

  const tokenResponse = await request.post(`${mcpBaseUrl}/oauth/token`, {
    form: {
      grant_type: 'authorization_code',
      code,
      redirect_uri: redirectUri,
      client_id: clientId,
      code_verifier: verifier,
      resource,
    },
  });
  expect(tokenResponse.ok()).toBeTruthy();
  const token = (await tokenResponse.json()) as { access_token?: string };
  const accessToken = String(token.access_token ?? '');
  expect(accessToken).not.toBe('');
  return { accessToken, userId: jwtSubject(accessToken) };
}

async function discoverLawThroughMcp(
  request: APIRequestContext,
  accessToken: string,
): Promise<McpSource> {
  const searchPayload = await callMcpTool(request, accessToken, 'searchLaws', {
    query: scenario.law.identifier,
    country_code: scenario.countryCode,
    law_number: scenario.law.number,
    law_year: scenario.law.year,
    sort: 'relevance',
    limit: 5,
  });
  const results = Array.isArray(searchPayload.results)
    ? (searchPayload.results as Array<Record<string, unknown>>)
    : [];
  const result = results.find((item) => lawResultMatches(item));
  expect(result, `MCP searchLaws must return ${scenario.law.identifier}`).toBeTruthy();
  const documentId = String(result?.document_id ?? '');
  expect(documentId).not.toBe('');
  const title = String(result?.title ?? result?.official_name ?? result?.lawyer_title ?? '').trim();
  const sourceUrl = String(result?.source_url ?? '').trim();
  expect(title, 'MCP law title is required for the deterministic answer contract').not.toBe('');
  expect(sourceUrl, 'MCP official source URL is required for citation verification').toMatch(/^https:\/\//);

  const textPayload = await callMcpTool(request, accessToken, 'getLawText', {
    document_id: documentId,
    offset: 0,
    max_chars: 4000,
  });
  const content = String(
    textPayload.content_text ?? textPayload.text ?? textPayload.content ?? textPayload.law_text ?? '',
  ).trim();
  expect(content.length, 'MCP getLawText must return bounded non-empty law text').toBeGreaterThan(40);

  return {
    documentId,
    identifier: String(
      result?.law_identifier_text ?? result?.law_identifier ?? result?.identifier ?? scenario.law.identifier,
    ),
    title,
    sourceUrl,
    textCharacters: content.length,
  };
}

async function discoverLatestLawsThroughMcp(
  request: APIRequestContext,
  accessToken: string,
  question: string,
): Promise<McpSource[]> {
  const payload = await callMcpTool(request, accessToken, 'searchLaws', {
    query: question,
    country_code: scenario.countryCode,
    sort: 'latest',
    limit: 5,
    include_summaries: true,
  });
  const results = Array.isArray(payload.results)
    ? (payload.results as Array<Record<string, unknown>>).slice(0, 5)
    : [];
  expect(results, 'MCP must return exactly five current laws for the production stability scenario').toHaveLength(5);
  return results.map((result) => {
    const documentId = String(result.document_id ?? '');
    const identifier = String(
      result.law_identifier_text ?? result.law_identifier ?? result.identifier ?? '',
    ).trim();
    const summary = String(result.summary ?? result.ai_summary ?? result.description ?? '').trim();
    expect(documentId).not.toBe('');
    expect(identifier).not.toBe('');
    expect(summary, `MCP result ${identifier} must expose a summary`).not.toBe('');
    return {
      documentId,
      identifier,
      title: String(result.title ?? result.official_name ?? identifier),
      sourceUrl: String(result.source_url ?? ''),
      textCharacters: summary.length,
      summary,
    };
  });
}

async function callMcpTool(
  request: APIRequestContext,
  accessToken: string,
  name: string,
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const response = await request.post(`${mcpBaseUrl}/MCP`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Accept: 'application/json, text/event-stream',
      'Content-Type': 'application/json',
      'MCP-Protocol-Version': '2025-11-25',
      'x-request-id': randomUUID(),
      'x-correlation-id': randomUUID(),
    },
    data: {
      jsonrpc: '2.0',
      id: randomUUID(),
      method: 'tools/call',
      params: { name, arguments: args },
    },
    timeout: timeoutMs,
  });
  expect(response.ok(), `${name} MCP call failed with HTTP ${response.status()}`).toBeTruthy();
  const envelope = (await response.json()) as {
    error?: unknown;
    result?: { content?: Array<{ type?: string; text?: string }> };
  };
  expect(envelope.error).toBeUndefined();
  const textBlock = envelope.result?.content?.find((item) => item.type === 'text')?.text ?? '';
  expect(textBlock).not.toBe('');
  const payload = JSON.parse(textBlock) as Record<string, unknown>;
  expect(String(payload.status ?? 'ok')).not.toBe('degraded');
  return payload;
}

async function removePriorSyntheticCases(request: APIRequestContext, userId: string): Promise<void> {
  const response = await request.get(
    `${apiBaseUrl}/v1/cases?user_id=${encodeURIComponent(userId)}`,
    { headers: apiHeaders() },
  );
  expect(response.ok()).toBeTruthy();
  const cases = (await response.json()) as Array<{ case_id?: string; title?: string }>;
  for (const candidate of cases.filter((item) => String(item.title ?? '').startsWith('[issue-646-'))) {
    const id = String(candidate.case_id ?? '');
    if (id) {
      await request.delete(
        `${apiBaseUrl}/v1/cases/${encodeURIComponent(id)}?user_id=${encodeURIComponent(userId)}`,
        { headers: apiHeaders() },
      );
    }
  }
}

async function waitForSyntheticCasePersistence(
  request: APIRequestContext,
  userId: string,
  caseId: string,
  caseTitle: string,
): Promise<void> {
  await expect
    .poll(
      async () => {
        const response = await request.get(
          `${apiBaseUrl}/v1/cases?user_id=${encodeURIComponent(userId)}`,
          { headers: apiHeaders() },
        );
        if (!response.ok()) {
          return `case-list-api-${response.status()}`;
        }
        const cases = (await response.json()) as Array<{ case_id?: string; title?: string }>;
        return cases.some((item) => String(item.case_id ?? '') === caseId && String(item.title ?? '') === caseTitle)
          ? 'persisted'
          : `case-not-listed-${cases.length}`;
      },
      {
        message: `Synthetic case ${caseId} was created but did not become visible through the authorized case-list API`,
        timeout: 30_000,
        intervals: [500, 1_000, 2_000],
      },
    )
    .toBe('persisted');
}

async function openSyntheticCaseInFrontend(page: Page, caseId: string, caseTitle: string): Promise<void> {
  const caseUrl = `${frontendBaseUrl}/case/${encodeURIComponent(caseId)}`;
  let lastError = '';

  for (let attempt = 1; attempt <= 3; attempt += 1) {
    await page.goto(caseUrl, { waitUntil: 'domcontentloaded', timeout: 120_000 });
    try {
      await expect(page.getByText(caseTitle, { exact: true })).toBeVisible({ timeout: 20_000 });
      await expect(page.locator('.assistant-composer__input')).toBeVisible({ timeout: 20_000 });
      return;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
  }

  throw new Error(
    `Synthetic case ${caseId} is persisted but was not rendered by the frontend after three direct deep-link attempts: ${lastError}`,
  );
}

async function seedFrontendSession(page: Page, userId: string, email: string): Promise<void> {
  await page.addInitScript(
    ({ key, id, address }) => {
      window.localStorage.setItem('aj_frontend_lang', 'sk');
      window.sessionStorage.setItem(
        key,
        JSON.stringify({
          userId: id,
          email: address,
          name: 'JurisDigta Synthetic Post-deployment E2E',
          role: 'user',
          isEnabled: true,
        }),
      );
    },
    { key: authSessionKey, id: userId, address: email },
  );
}

function lawResultMatches(result: Record<string, unknown>): boolean {
  const number = Number(result.law_number ?? 0);
  const year = Number(result.law_year ?? 0);
  const identifiers = [
    result.law_identifier_text,
    result.law_identifier,
    result.identifier,
    result.title,
  ]
    .map((value) => String(value ?? ''))
    .join(' ');
  return (
    (number === scenario.law.number && year === scenario.law.year) ||
    identifiers.includes(scenario.law.identifier)
  );
}

function citationMatchesDirectMcp(citation: CaseCitation, directMcp: McpSource): boolean {
  const sourceId = String(citation.source_id ?? '');
  return (
    String(citation.source_type ?? '').toLowerCase() === 'law' &&
    sourceId === directMcp.documentId &&
    String(citation.law_number ?? citation.citation_label ?? '').includes(scenario.law.identifier) &&
    /JurisDigta MCP/i.test(String(citation.retrieval_tool ?? ''))
  );
}

function jwtSubject(token: string): string {
  const parts = token.split('.');
  expect(parts.length).toBe(3);
  const payload = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8')) as {
    sub?: string;
    user_id?: string;
  };
  const subject = String(payload.sub ?? payload.user_id ?? '');
  expect(subject).toMatch(/^[0-9a-f-]{36}$/i);
  return subject;
}

function normalizeProvider(provider: string): string {
  return provider.trim().toLowerCase().replace(/[^a-z0-9]/g, '');
}

function sha256(value: string): string {
  return createHash('sha256').update(value, 'utf8').digest('hex');
}

function safePreview(value: string): string {
  return value.replace(/\s+/g, ' ').trim().slice(0, 500);
}

function sanitizeError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  return message
    .replace(/Bearer\s+[A-Za-z0-9._~+\/-]+/gi, 'Bearer [REDACTED]')
    .replace(/(?:password|access_token|refresh_token)\s*[=:]\s*[^\s,}]+/gi, '$1=[REDACTED]')
    .slice(0, 2000);
}
