import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { createHash, randomBytes, randomUUID } from 'crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

type Scenario = {
  schemaVersion: number;
  scenarioId: string;
  countryCode: string;
  courtDecision: {
    query: string;
    question: string;
    limit: number;
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
  decisionId: string;
  sourceGuid: string;
  courtName: string;
  issueDate: string;
  ecli: string;
  fileNumber: string;
  sourceUrl: string;
  issueDateStatus: string;
};

type McpDiscovery = {
  sources: McpSource[];
  coverageNotice: string;
  latestLabelSafe: boolean;
  invalidOrMissingIssueDates: number;
};

type CaseCitation = {
  source_type?: string | null;
  source_id?: string | null;
  source_url?: string | null;
  title?: string | null;
  citation_label?: string | null;
  law_number?: string | null;
  court?: string | null;
  ecli?: string | null;
  file_number?: string | null;
  decision_date?: string | null;
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
  directMcp?: McpSource[];
  mcpDataQuality?: {
    coverageNotice: string;
    latestLabelSafe: boolean;
    invalidOrMissingIssueDates: number;
  };
  observedCitations?: Array<{
    sourceId: string;
    sourceUrl: string;
    court: string;
    ecli: string;
    fileNumber: string;
    decisionDate: string;
    retrievalTool: string;
  }>;
  aiWebSearchAgentUsed?: boolean;
  answerSha256?: string;
  modelAudit?: ModelAuditEntry;
  screenshot?: string;
  error?: string;
};

const scenario = JSON.parse(
  readFileSync(join(process.cwd(), 'tests', 'fixtures', 'issue-647-prod-mcp-court-decisions.json'), 'utf8'),
) as Scenario;
const apiBaseUrl = (process.env.API_BASE_URL ?? 'https://api.jurisdigta.eu').replace(/\/$/, '');
const frontendBaseUrl = (process.env.FRONTEND_BASE_URL ?? 'https://web.jurisdigta.eu').replace(/\/$/, '');
const mcpBaseUrl = (process.env.MCP_PUBLIC_BASE_URL ?? 'https://mcp.jurisdigta.eu').replace(/\/$/, '');
const apiKey = process.env.API_KEY?.trim() || 'aijuris';
const e2ePassword = process.env.JURISDIGTA_E2E_TEST_USER_PASSWORD?.trim() || '';
const expectedCommitSha = process.env.ISSUE_647_DEPLOYED_COMMIT_SHA?.trim() || '';
const timeoutMs = Number(process.env.ISSUE_647_TIMEOUT_MS ?? 660_000);
const finalScreenshotPath = process.env.ISSUE_647_FINAL_SCREENSHOT_PATH?.trim() || '';
const authSessionKey = 'jurisdigta.web.auth.user.v1';

test.describe.configure({ mode: 'serial' });

test('production MCP court-decision grounding is preserved through Azure Foundry gpt-5-mini', async ({
  browser,
  request,
}, testInfo) => {
  test.setTimeout(timeoutMs * scenario.modelMatrix.length + 180_000);
  expect(e2ePassword, 'JURISDIGTA_E2E_TEST_USER_PASSWORD must be supplied securely').not.toBe('');
  expect(e2ePassword).not.toBe('unknown-variable');
  expect(expectedCommitSha, 'ISSUE_647_DEPLOYED_COMMIT_SHA is required for deployment traceability').toMatch(
    /^[0-9a-f]{40}$/i,
  );

  const versionResponse = await request.get(`${apiBaseUrl}/version`, { headers: apiHeaders() });
  expect(versionResponse.ok()).toBeTruthy();
  const version = (await versionResponse.json()) as Record<string, unknown>;
  const runId = `issue-647-${new Date().toISOString().replace(/[:.]/g, '-')}-${randomUUID().slice(0, 8)}`;
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
      const discovery = await discoverCourtDecisionsThroughMcp(request, oauth.accessToken);
      const directMcp = discovery.sources;
      result.directMcp = directMcp;
      result.mcpDataQuality = {
        coverageNotice: discovery.coverageNotice,
        latestLabelSafe: discovery.latestLabelSafe,
        invalidOrMissingIssueDates: discovery.invalidOrMissingIssueDates,
      };

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
      const caseTitle = `[${runId}] MCP court decisions ${cell.id}`;
      const caseResponse = await request.post(`${apiBaseUrl}/v1/cases`, {
        headers: apiHeaders(),
        data: { user_id: userId, title: caseTitle },
      });
      expect(caseResponse.status()).toBe(201);
      const createdCase = (await caseResponse.json()) as Record<string, unknown>;
      caseId = String(createdCase.case_id ?? '');
      expect(caseId).not.toBe('');

      await seedFrontendSession(page, userId, cell.email);
      await page.goto(`${frontendBaseUrl}/app/assistant`, { waitUntil: 'domcontentloaded', timeout: 120_000 });
      await page.getByText(caseTitle, { exact: true }).click({ timeout: 60_000 });
      await expect(page.locator('.assistant-model-disclosure')).toContainText(
        new RegExp(escapeRegex(cell.expectedModel), 'i'),
        { timeout: 60_000 },
      );
      await page.locator('.assistant-composer__input').fill(scenario.courtDecision.question);
      await page.locator('.assistant-composer__send').click();
      const completedAssistantMessage = page.locator('.assistant-message').last();
      await expect(completedAssistantMessage).toContainText(/súd|rozhodnut/i, { timeout: timeoutMs });
      await expect(page.locator('.assistant-tool-panel')).toContainText(/JurisDigta MCP/i, {
        timeout: timeoutMs,
      });
      await expect(
        page.locator('.assistant-tool-panel').getByText('JurisDigta MCP searchCourtDecisions'),
      ).toHaveCount(scenario.courtDecision.limit, { timeout: timeoutMs });
      for (const source of directMcp) {
        await expect(page.locator('.assistant-tool-panel')).toContainText(source.courtName);
        await expect(page.locator('.assistant-tool-panel')).toContainText(source.issueDate);
        await expect(page.locator('.assistant-tool-panel')).toContainText(source.ecli || source.fileNumber);
      }

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
      expect(answer).not.toBe('');
      for (const source of directMcp) {
        expect(answer).toContain(source.courtName);
        expect(answer).toContain(source.ecli || source.fileNumber);
      }
      expect(answer).toMatch(/judikatúr|súdne rozhodnut/i);
      expect(answer).toMatch(/nezáväzn|nie (?:je|sú) záväzn|podporn/i);
      expect(answer).toMatch(/korpus|pokryti|dostupn/i);
      expect(answer).toMatch(/ľudsk|právn.{0,20}(?:kontrol|over)/i);
      if (!discovery.latestLabelSafe) {
        expect(answer).toMatch(/dátum|dátumov|chýba|neplatn|chronolog/i);
      }
      const citations = history.citations ?? [];
      const mcpCitations = directMcp.map((source) => {
        const citation = citations.find((candidate) => citationMatchesDirectMcp(candidate, source));
        expect(citation, `Persisted citation must match MCP decision ${source.decisionId}`).toBeTruthy();
        expect(String(citation?.source_url ?? '')).toBe(source.sourceUrl);
        expect(String(citation?.court ?? '')).toBe(source.courtName);
        expect(String(citation?.decision_date ?? '')).toBe(source.issueDate);
        expect(String(citation?.ecli || citation?.file_number || '')).toContain(source.ecli || source.fileNumber);
        return citation as CaseCitation;
      });
      expect(new Set(mcpCitations.map((citation) => citation.source_id)).size).toBe(scenario.courtDecision.limit);
      const aiWebSearchAgentUsed = citations.some(
        (citation) =>
          String(citation.source_type ?? '').toLowerCase() === 'web' ||
          /AIWebSearchAgent/i.test(String(citation.retrieval_tool ?? '')),
      );
      expect(aiWebSearchAgentUsed, 'AIWebSearchAgent/web fallback must not satisfy this MCP test').toBe(false);
      for (const citation of mcpCitations) {
        expect(String(citation.retrieval_tool ?? '')).toMatch(/JurisDigta MCP searchCourtDecisions/i);
      }

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

      result.observedCitations = mcpCitations.map((citation) => ({
        sourceId: String(citation.source_id ?? ''),
        sourceUrl: String(citation.source_url ?? ''),
        court: String(citation.court ?? ''),
        ecli: String(citation.ecli ?? ''),
        fileNumber: String(citation.file_number ?? ''),
        decisionDate: String(citation.decision_date ?? ''),
        retrievalTool: String(citation.retrieval_tool ?? ''),
      }));
      result.aiWebSearchAgentUsed = aiWebSearchAgentUsed;
      result.answerSha256 = sha256(answer);
      result.modelAudit = modelAudit;
      result.status = 'passed';
    } catch (error) {
      result.error = sanitizeError(error);
    } finally {
      const screenshotName = `issue-647-${cell.id}-${result.status}.png`;
      const screenshotPath = testInfo.outputPath(screenshotName);
      try {
        await page.screenshot({ path: screenshotPath, fullPage: true });
        result.screenshot = screenshotName;
        if (finalScreenshotPath) {
          mkdirSync(dirname(finalScreenshotPath), { recursive: true });
          await page.screenshot({ path: finalScreenshotPath, fullPage: true });
        }
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
    questionSha256: sha256(scenario.courtDecision.question),
    deterministicContract: {
      exactProseRequired: false,
      requiredDecisionCount: scenario.courtDecision.limit,
      requiredSameMcpDecisionIds: true,
      metadataOnlyExternalRoute: true,
      internalRawBlocked: true,
      humanReviewRequired: true,
      aiWebSearchAgentAllowed: false,
    },
    corpusCoverage: 'Latest means the latest matching decisions available in JurisDigta, not complete national coverage.',
    matrix: matrixResults,
    retention: 'Delete this ignored evidence within 7 days.',
  };
  const manifestPath = testInfo.outputPath('issue-647-result-manifest.json');
  writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
  await testInfo.attach('issue-647-result-manifest', {
    path: manifestPath,
    contentType: 'application/json',
  });
  for (const result of matrixResults) {
    if (result.screenshot) {
      await testInfo.attach(`issue-647-${result.id}`, {
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
      client_name: 'JurisDigta issue 647 post-deployment E2E',
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

async function discoverCourtDecisionsThroughMcp(
  request: APIRequestContext,
  accessToken: string,
): Promise<McpDiscovery> {
  const searchPayload = await callMcpTool(request, accessToken, 'searchCourtDecisions', {
    query: scenario.courtDecision.query,
    sort: 'latest',
    limit: scenario.courtDecision.limit,
    include_snippets: false,
    include_summaries: false,
  });
  expect(searchPayload.metadata_only, 'searchCourtDecisions must remain metadata-only').toBe(true);
  expect(searchPayload.output_mode).toBe('public');
  expect(searchPayload.sort).toBe('latest');
  const coverageNotice = String(searchPayload.coverage_notice ?? '');
  expect(coverageNotice).toMatch(/JurisDigta corpus/i);
  const dataQuality = searchPayload.data_quality as Record<string, unknown> | undefined;
  expect(typeof dataQuality?.latest_label_safe).toBe('boolean');
  const latestLabelSafe = Boolean(dataQuality?.latest_label_safe);
  const invalidOrMissingIssueDates = Number(dataQuality?.invalid_or_missing_issue_date_results ?? 0);
  expect(invalidOrMissingIssueDates).toBeGreaterThanOrEqual(0);
  const results = Array.isArray(searchPayload.results)
    ? (searchPayload.results as Array<Record<string, unknown>>)
    : [];
  const sources: McpSource[] = [];
  for (const result of results) {
    expect(result.output_mode).toBe('public');
    expect(result.snippet).toBeUndefined();
    expect(result.summary).toBeUndefined();
    const decisionId = String(result.decision_id ?? '');
    expect(decisionId).not.toBe('');
    const metadata = await callMcpTool(request, accessToken, 'getCourtDecision', {
      decision_id: decisionId,
      full_version: false,
      outputMode: 'public',
      enrich_if_missing: false,
    });
    expect(metadata.metadata_only).toBe(true);
    expect(metadata.full_version).toBe(false);
    expect(metadata.output_mode).toBe('public');
    expect(metadata.text).toBeUndefined();
    expect(metadata.snippet).toBeUndefined();
    expect(metadata.summary).toBeUndefined();

    const source: McpSource = {
      decisionId,
      sourceGuid: String(metadata.source_guid ?? result.source_guid ?? ''),
      courtName: String(metadata.court_name ?? result.court_name ?? ''),
      issueDate: String(metadata.issue_date ?? result.issue_date ?? ''),
      ecli: String(metadata.ecli ?? result.ecli ?? ''),
      fileNumber: String(metadata.file_number ?? result.file_number ?? ''),
      sourceUrl: String(metadata.source_url ?? result.source_url ?? ''),
      issueDateStatus: String(metadata.issue_date_status ?? result.issue_date_status ?? ''),
    };
    expect(source.sourceGuid).not.toBe('');
    expect(source.courtName).not.toBe('');
    expect(source.issueDate).not.toBe('');
    expect(source.ecli || source.fileNumber, 'Each decision needs an ECLI or file number').not.toBe('');
    expect(source.sourceUrl).toMatch(/^https:\/\//);
    sources.push(source);
  }
  if (sources.length > 0) {
    await expectInternalRawBlocked(request, accessToken, sources[0].decisionId);
  }
  return { sources, coverageNotice, latestLabelSafe, invalidOrMissingIssueDates };
}

async function expectInternalRawBlocked(
  request: APIRequestContext,
  accessToken: string,
  decisionId: string,
): Promise<void> {
  const response = await request.post(`${mcpBaseUrl}/MCP`, {
    headers: mcpHeaders(accessToken),
    data: {
      jsonrpc: '2.0',
      id: randomUUID(),
      method: 'tools/call',
      params: {
        name: 'getCourtDecision',
        arguments: { decision_id: decisionId, outputMode: 'internal_raw' },
      },
    },
    timeout: timeoutMs,
  });
  if (response.status() === 403) {
    return;
  }
  expect(response.ok()).toBeTruthy();
  const envelope = (await response.json()) as { error?: unknown; result?: { isError?: boolean; content?: unknown } };
  expect(
    envelope.error ?? (envelope.result?.isError ? envelope.result.content : undefined),
    'External MCP route must reject outputMode=internal_raw',
  ).toBeTruthy();
  expect(JSON.stringify(envelope)).toMatch(/internal_raw|not enabled|403/i);
}

async function callMcpTool(
  request: APIRequestContext,
  accessToken: string,
  name: string,
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const response = await request.post(`${mcpBaseUrl}/MCP`, {
    headers: mcpHeaders(accessToken),
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

function mcpHeaders(accessToken: string): Record<string, string> {
  return {
    Authorization: `Bearer ${accessToken}`,
    Accept: 'application/json, text/event-stream',
    'Content-Type': 'application/json',
    'MCP-Protocol-Version': '2025-11-25',
    'x-request-id': randomUUID(),
    'x-correlation-id': randomUUID(),
  };
}

async function removePriorSyntheticCases(request: APIRequestContext, userId: string): Promise<void> {
  const response = await request.get(
    `${apiBaseUrl}/v1/cases?user_id=${encodeURIComponent(userId)}`,
    { headers: apiHeaders() },
  );
  expect(response.ok()).toBeTruthy();
  const cases = (await response.json()) as Array<{ case_id?: string; title?: string }>;
  for (const candidate of cases.filter((item) => String(item.title ?? '').startsWith('[issue-647-'))) {
    const id = String(candidate.case_id ?? '');
    if (id) {
      await request.delete(
        `${apiBaseUrl}/v1/cases/${encodeURIComponent(id)}?user_id=${encodeURIComponent(userId)}`,
        { headers: apiHeaders() },
      );
    }
  }
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

function citationMatchesDirectMcp(citation: CaseCitation, directMcp: McpSource): boolean {
  const sourceId = String(citation.source_id ?? '');
  return (
    String(citation.source_type ?? '').toLowerCase() === 'court_decision' &&
    (sourceId === directMcp.decisionId || sourceId === directMcp.sourceGuid) &&
    String(citation.source_url ?? '') === directMcp.sourceUrl &&
    /JurisDigta MCP searchCourtDecisions/i.test(String(citation.retrieval_tool ?? ''))
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

function sanitizeError(error: unknown): string {
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  return message
    .replace(/\u001b\[[0-9;]*m/g, '')
    .replace(/Bearer\s+[A-Za-z0-9._~+\/-]+/gi, 'Bearer [REDACTED]')
    .replace(/(?:password|access_token|refresh_token)\s*[=:]\s*[^\s,}]+/gi, '$1=[REDACTED]')
    .slice(0, 2000);
}
