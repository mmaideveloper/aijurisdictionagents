import { APIRequestContext, expect, test } from '@playwright/test';
import { execFile } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';
import { ensureLiveApiOrFail } from './helpers/liveApi';

const execFileAsync = promisify(execFile);
const apiKey = process.env.API_KEY ?? 'aijuris';
const e2eRoot = path.resolve(__dirname, '..');
const apiRoot = path.resolve(e2eRoot, '..');
const repoRoot = path.resolve(apiRoot, '..', '..');
const currentWorktreePythonPath = [path.join(repoRoot, 'src'), apiRoot].join(path.delimiter);
const fixturePath = path.join(
  repoRoot,
  'api',
  'chat-simulator-app',
  'testcases',
  'outdated-najomna-zmluva-2026.txt'
);
const expectedPath = path.join(
  repoRoot,
  'api',
  'chat-simulator-app',
  'testcases',
  'outdated-najomna-zmluva-2026.expected.json'
);
const liveTimeoutMs = Number(process.env.OUTDATED_RENTAL_E2E_TIMEOUT_MS ?? 360_000);

type CreatedUser = {
  user_id: string;
  email: string;
};

type CreatedCase = {
  case_id: string;
};

type ChatSession = {
  id: string;
  user_id: string;
  case_id?: string;
};

type EffectiveRoute = {
  plan_code: string;
  route_type: string;
  provider: string;
  model: string;
  is_local: boolean;
  is_external: boolean;
};

type CheckoutResponse = {
  subscription_id: string;
  payment_id: string;
};

type ChatMessage = {
  role: string;
  content: string;
};

type CaseHistory = {
  messages: Array<{ role: string; content: string; agent_name: string | null }>;
  documents: Array<{ doc_id: string; kind: string; original_filename: string; processing_status: string }>;
};

type DocumentDebug = {
  stored_documents: Array<{ original_filename: string; processing_status: string; extracted_characters: number }>;
  selected_prompt_chunks: Array<{ content: string; path: string }>;
  prompt_preview: string;
};

type DocumentExportOptions = {
  documents: {
    index: number;
    filename: string;
    title: string;
  }[];
};

type ExpectedFixture = {
  expectedExtractedFields: Record<string, string>;
  knownOutdatedThemes: Array<{
    id: string;
    keywords: string[];
    expectedLawHints: string[];
  }>;
  forbiddenMissingDataQuestions: string[];
  lawGroundingHints: string[];
};

type TestVariant = {
  name: 'free' | 'paid';
  title: string;
};

const variants: TestVariant[] = [
  { name: 'free', title: 'Free local model route' },
  { name: 'paid', title: 'Paid Case-plan route' },
];

test.beforeEach(async ({ request, baseURL }) => {
  await ensureLiveApiOrFail(request, baseURL);
});

for (const variant of variants) {
  test(`${variant.title} updates an outdated Slovak rental agreement with law-grounded changes`, async ({
    request,
    baseURL,
  }) => {
    test.setTimeout(liveTimeoutMs);

    const expected = await loadExpectedFixture();
    await expectLiveLawsCorpus(request, baseURL);

    const runId = Date.now() + Math.floor(Math.random() * 1000);
    const user = await createSyntheticUser(request, baseURL, runId, variant.name);
    if (variant.name === 'paid') {
      await activateCasePlan(request, baseURL, user.user_id);
    }

    const route = await getEffectiveRoute(request, baseURL, user.user_id);
    expectRouteMatchesVariant(route, variant);

    const createdCase = await createCase(
      request,
      baseURL,
      user.user_id,
      `E2E outdated rental ${variant.name} ${runId}`
    );
    await uploadOutdatedRentalAgreement(request, baseURL, user.user_id, createdCase.case_id);

    const debug = await getDocumentDebug(request, baseURL, user.user_id, createdCase.case_id);
    expect(debug.stored_documents[0]).toMatchObject({
      original_filename: 'outdated-najomna-zmluva-2026.txt',
      processing_status: 'processed',
    });
    expect(debug.stored_documents[0].extracted_characters).toBeGreaterThan(2500);
    expect(canonical(debug.prompt_preview)).toContain('marek testovany');
    expect(canonical(debug.prompt_preview)).toContain('eva najomna');

    const session = await createSession(request, baseURL, user.user_id, createdCase.case_id);
    const assistantMessages: ChatMessage[] = [];

    assistantMessages.push(
      await sendReply(
        request,
        baseURL,
        session.id,
        [
          'Analyzuj vsetky nahrane dokumenty v tomto pripade.',
          'Over zastaranu najomnu zmluvu podla aktualnych slovenskych zakonov z JurisDigta laws/RAG databazy.',
          'Zobraz udaje, ktore si nasiel v starej zmluve.',
          'Navrhni zmeny a kazdu materialnu zmenu odovodni zakonom.',
          'Priprav opraveny navrh najomnej zmluvy.',
          'Nepytaj sa na prenajimatela, najomcu, byt, najomne, zabezpeku ani dobu najmu, ak su citatelne v dokumente.',
        ].join(' ')
      )
    );

    const firstReply = visibleText(assistantMessages[0].content);
    expectExtractedFields(firstReply, expected);
    expectDoesNotAskForKnownData(firstReply, expected);

    assistantMessages.push(
      await sendReply(
        request,
        baseURL,
        session.id,
        [
          'Suhlasim, pouzi udaje najdene v starej zmluve.',
          'Neziadaj znovu udaje, ktore boli v dokumente.',
          'Vygeneruj finalny opraveny navrh najomnej zmluvy vo formate PDF na stiahnutie.',
          'V odpovedi ponechaj aj strucny zoznam navrhovanych zmien s odkazom na zakon.',
        ].join(' ')
      )
    );

    const combinedAssistantText = visibleText(assistantMessages.map((message) => message.content).join('\n\n'));
    expectExtractedFields(combinedAssistantText, expected);
    expectDoesNotAskForKnownData(combinedAssistantText, expected);
    expectSuggestedChangesAreGrounded(combinedAssistantText, expected);

    const exports = await pollDocumentExports(request, baseURL, session.id);
    expect(exports.documents.length).toBeGreaterThanOrEqual(1);

    const pdf = await request.get(`${baseURL}/v1/chat/sessions/${session.id}/export/documents/${exports.documents[0].index}`, {
      headers: { 'x-api-key': apiKey },
      timeout: liveTimeoutMs,
    });
    expect(pdf.status()).toBe(200);
    expect(pdf.headers()['content-type']).toContain('application/pdf');
    const pdfText = await extractPdfText(Buffer.from(await pdf.body()));
    const normalizedPdf = canonical(pdfText);

    expect(normalizedPdf).toContain('marek testovany');
    expect(normalizedPdf).toContain('eva najomna');
    expect(normalizedPdf).toContain('dunajska 45');
    expect(normalizedPdf).toContain('850 eur');
    expect(normalizedPdf).toContain('1 700 eur');
    expect(normalizedPdf).toContain('1. jula 2026');
    expect(normalizedPdf).toContain('30. juna 2027');
    expectNoUnresolvedPlaceholders(normalizedPdf);

    const history = await getCaseHistory(request, baseURL, user.user_id, createdCase.case_id);
    const historyText = visibleText(history.messages.map((message) => message.content).join('\n\n'));
    expectExtractedFields(historyText, expected);
    expect(history.documents.some((document) => document.original_filename === 'outdated-najomna-zmluva-2026.txt')).toBeTruthy();
  });
}

async function loadExpectedFixture(): Promise<ExpectedFixture> {
  return JSON.parse(await readFile(expectedPath, 'utf8')) as ExpectedFixture;
}

async function expectLiveLawsCorpus(request: APIRequestContext, baseURL: string | undefined): Promise<void> {
  const response = await request.get(`${baseURL}/version`, {
    headers: { 'x-api-key': apiKey },
    timeout: 10_000,
  });
  expect(response.status()).toBe(200);
  const payload = (await response.json()) as {
    laws_by_country?: {
      sk?: {
        last_law_update_source?: string | null;
        last_processed_law?: string | null;
      };
    };
  };
  const sk = payload.laws_by_country?.sk;
  expect(sk, `Expected /version to expose SK laws corpus metadata. Payload: ${JSON.stringify(payload)}`).toBeTruthy();
  expect(sk?.last_law_update_source || sk?.last_processed_law).toBeTruthy();
  const corpusStatus = canonical(`${sk?.last_law_update_source ?? ''} ${sk?.last_processed_law ?? ''}`);
  if (corpusStatus.includes('unavailable')) {
    throw new Error(
      'Live SK laws corpus is unavailable to the API. Start the API with LAWS_DB_BACKEND=postgres ' +
        'and LAWS_DB_CLOUD=postgresql://postgres:postgres@127.0.0.1:5433/laws_sk, or point it to an equivalent ' +
        `live laws collector database. /version SK payload: ${JSON.stringify(sk)}`
    );
  }
}

async function createSyntheticUser(
  request: APIRequestContext,
  baseURL: string | undefined,
  runId: number,
  variant: string
): Promise<CreatedUser> {
  const response = await request.post(`${baseURL}/v1/users/sign-up`, {
    headers: { 'x-api-key': apiKey },
    data: {
      phone_number: `+421905${String(runId).slice(-6)}`,
      email: `outdated-rental-${variant}.${runId}@example.test`,
      password: 'secret',
      first_name: 'E2E',
      last_name: `Rental ${variant}`,
      data_processing_consent_accepted: true,
      data_processing_consent_version: 'e2e-outdated-rental-2026-06-28',
    },
  });
  expect(response.status()).toBe(201);
  return (await response.json()) as CreatedUser;
}

async function activateCasePlan(
  request: APIRequestContext,
  baseURL: string | undefined,
  userId: string
): Promise<void> {
  const checkoutResponse = await request.post(`${baseURL}/v1/users/${userId}/subscriptions/checkout`, {
    headers: { 'x-api-key': apiKey },
    data: { plan_code: 'case', payment_provider: 'paypal' },
    timeout: 30_000,
  });
  if (checkoutResponse.status() !== 201) {
    throw new Error(
      `Case-plan checkout must be enabled for the paid outdated-rental E2E. ` +
        `Status: ${checkoutResponse.status()}. Body: ${await checkoutResponse.text()}`
    );
  }
  const checkout = (await checkoutResponse.json()) as CheckoutResponse;

  const confirmResponse = await request.post(
    `${baseURL}/v1/users/subscriptions/${checkout.subscription_id}/confirm-payment`,
    {
      headers: { 'x-api-key': apiKey },
      data: { payment_id: checkout.payment_id },
      timeout: 30_000,
    }
  );
  expect(confirmResponse.status()).toBe(200);
  await expect(confirmResponse.json()).resolves.toMatchObject({
    plan_code: 'case',
    status: 'paid',
  });
}

async function createCase(
  request: APIRequestContext,
  baseURL: string | undefined,
  userId: string,
  title: string
): Promise<CreatedCase> {
  const response = await request.post(`${baseURL}/v1/cases`, {
    headers: { 'x-api-key': apiKey },
    data: {
      user_id: userId,
      title,
    },
  });
  expect(response.status()).toBe(201);
  return (await response.json()) as CreatedCase;
}

async function uploadOutdatedRentalAgreement(
  request: APIRequestContext,
  baseURL: string | undefined,
  userId: string,
  caseId: string
): Promise<void> {
  const buffer = await readFile(fixturePath);
  const response = await request.post(`${baseURL}/v1/cases/${caseId}/documents?user_id=${userId}`, {
    headers: { 'x-api-key': apiKey },
    multipart: {
      files: {
        name: 'outdated-najomna-zmluva-2026.txt',
        mimeType: 'text/plain',
        buffer,
      },
    },
    timeout: 60_000,
  });
  expect(response.status()).toBe(201);
  const payload = (await response.json()) as { uploaded: Array<{ processing_status: string }> };
  expect(payload.uploaded[0].processing_status).toBe('processed');
}

async function getDocumentDebug(
  request: APIRequestContext,
  baseURL: string | undefined,
  userId: string,
  caseId: string
): Promise<DocumentDebug> {
  const response = await request.get(
    `${baseURL}/v1/cases/${caseId}/documents/debug?user_id=${userId}&query=${encodeURIComponent(
      'analyze all uploaded documents and extract all rental agreement facts'
    )}`,
    {
      headers: { 'x-api-key': apiKey },
      timeout: 30_000,
    }
  );
  expect(response.status()).toBe(200);
  return (await response.json()) as DocumentDebug;
}

async function getEffectiveRoute(
  request: APIRequestContext,
  baseURL: string | undefined,
  userId: string
): Promise<EffectiveRoute> {
  const response = await request.get(`${baseURL}/v1/model-routing/effective?task_type=chat_reply&user_id=${userId}`, {
    headers: { 'x-api-key': apiKey },
    timeout: 30_000,
  });
  if (response.status() !== 200) {
    throw new Error(`Effective route failed. Status: ${response.status()}. Body: ${await response.text()}`);
  }
  return (await response.json()) as EffectiveRoute;
}

function expectRouteMatchesVariant(route: EffectiveRoute, variant: TestVariant): void {
  if (variant.name === 'free') {
    expect(route).toMatchObject({
      plan_code: 'free',
      route_type: 'free_local',
      is_local: true,
      is_external: false,
    });
    expect(canonical(route.provider)).toContain('local');
    return;
  }

  expect(route.plan_code).toBe('case');
  expect(route.route_type, `Paid Case plan should not be reported as the Free local route: ${JSON.stringify(route)}`).not.toBe(
    'free_local'
  );
}

async function createSession(
  request: APIRequestContext,
  baseURL: string | undefined,
  userId: string,
  caseId: string
): Promise<ChatSession> {
  const response = await request.post(`${baseURL}/v1/chat/sessions`, {
    headers: { 'x-api-key': apiKey },
    data: {
      user_id: userId,
      case_id: caseId,
      country: 'SK',
      language: 'sk',
      discussion_type: 'advice',
    },
  });
  expect(response.status()).toBe(200);
  return (await response.json()) as ChatSession;
}

async function sendReply(
  request: APIRequestContext,
  baseURL: string | undefined,
  sessionId: string,
  content: string
): Promise<ChatMessage> {
  const response = await request.post(`${baseURL}/v1/chat/sessions/${sessionId}/reply`, {
    headers: { 'x-api-key': apiKey },
    data: { content },
    timeout: liveTimeoutMs,
  });
  if (response.status() !== 200) {
    throw new Error(
      `Reply failed for prompt "${content}". Status: ${response.status()}. Body: ${await response.text()}`
    );
  }
  const message = (await response.json()) as ChatMessage;
  expect(message.role).toBe('assistant');
  expect(message.content.trim().length).toBeGreaterThan(80);
  return message;
}

async function pollDocumentExports(
  request: APIRequestContext,
  baseURL: string | undefined,
  sessionId: string
): Promise<DocumentExportOptions> {
  const deadline = Date.now() + 90_000;
  let lastExports: DocumentExportOptions | null = null;
  while (Date.now() < deadline) {
    const response = await request.get(`${baseURL}/v1/chat/sessions/${sessionId}/export/documents`, {
      headers: { 'x-api-key': apiKey },
      timeout: 30_000,
    });
    expect(response.status()).toBe(200);
    lastExports = (await response.json()) as DocumentExportOptions;
    if (lastExports.documents.length > 0) {
      return lastExports;
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error(`No corrected rental agreement export was produced. Last export payload: ${JSON.stringify(lastExports)}`);
}

async function getCaseHistory(
  request: APIRequestContext,
  baseURL: string | undefined,
  userId: string,
  caseId: string
): Promise<CaseHistory> {
  const response = await request.get(`${baseURL}/v1/cases/${caseId}/history?user_id=${userId}&limit=20`, {
    headers: { 'x-api-key': apiKey },
    timeout: 30_000,
  });
  expect(response.status()).toBe(200);
  return (await response.json()) as CaseHistory;
}

function expectExtractedFields(content: string, expected: ExpectedFixture): void {
  const normalized = canonical(content);
  const requiredFields = [
    'landlord',
    'tenant',
    'propertyAddress',
    'rent',
    'servicesAdvance',
    'deposit',
    'leaseStart',
    'leaseEnd',
    'iban',
  ];
  for (const key of requiredFields) {
    const value = expected.expectedExtractedFields[key];
    expect(normalized, `Expected extracted field ${key}=${value} in assistant output`).toContain(canonical(value));
  }
}

function expectDoesNotAskForKnownData(content: string, expected: ExpectedFixture): void {
  const normalized = canonical(content);
  for (const forbiddenQuestion of expected.forbiddenMissingDataQuestions) {
    expect(normalized, `Assistant asked for already-known field: ${forbiddenQuestion}`).not.toContain(
      canonical(forbiddenQuestion)
    );
  }
}

function expectSuggestedChangesAreGrounded(content: string, expected: ExpectedFixture): void {
  const normalized = canonical(content);
  for (const theme of expected.knownOutdatedThemes) {
    expect(
      theme.keywords.some((keyword) => normalized.includes(canonical(keyword))),
      `Assistant did not discuss outdated theme ${theme.id}`
    ).toBeTruthy();
  }

  expect(
    expected.lawGroundingHints.some((hint) => normalized.includes(canonical(hint))),
    `Assistant output did not include any expected law grounding hint: ${expected.lawGroundingHints.join(', ')}`
  ).toBeTruthy();
  expect(normalized).toMatch(/zakon|obciansk|paragraf|§|z\.\s*z|zb/);
}

function expectNoUnresolvedPlaceholders(normalizedText: string): void {
  expect(normalizedText).not.toMatch(/\[[^\]]+\]/);
  expect(normalizedText).not.toContain('doplnte');
  expect(normalizedText).not.toContain('chyba');
  expect(normalizedText).not.toContain('nezname');
  expect(normalizedText).not.toContain('xxx');
}

function visibleText(content: string): string {
  return content.replace(/CASE_UPDATE_JSON\s*:?\s*[\s\S]*$/i, '').trim();
}

async function extractPdfText(pdf: Buffer): Promise<string> {
  const tempDir = await mkdtemp(path.join(tmpdir(), 'jurisdigta-outdated-rental-'));
  const pdfPath = path.join(tempDir, 'document.pdf');
  await writeFile(pdfPath, pdf);
  const script = [
    'from pypdf import PdfReader',
    'import sys',
    'reader = PdfReader(sys.argv[1])',
    'print("\\n".join(page.extract_text() or "" for page in reader.pages))',
  ].join('\n');

  try {
    return await runPython(script, {}, [pdfPath]);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

async function runPython(
  script: string,
  extraEnv: Record<string, string>,
  args: string[] = []
): Promise<string> {
  const candidates = [
    process.env.PYTHON,
    process.env.API_PYTHON,
    path.resolve(process.cwd(), '..', '..', '..', 'conda', 'python.exe'),
    'python',
  ].filter(Boolean) as string[];
  const failures: string[] = [];

  for (const candidate of candidates) {
    try {
      const { stdout } = await execFileAsync(candidate, ['-c', script, ...args], {
        encoding: 'utf8',
        cwd: apiRoot,
        env: {
          ...process.env,
          ...extraEnv,
          PYTHONPATH: process.env.PYTHONPATH
            ? `${currentWorktreePythonPath}${path.delimiter}${process.env.PYTHONPATH}`
            : currentWorktreePythonPath,
          PYTHONIOENCODING: 'utf-8',
        },
        maxBuffer: 2_000_000,
      });
      return stdout;
    } catch (error) {
      failures.push(`${candidate}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  throw new Error(`No Python runtime was available for PDF e2e extraction. Failures:\n${failures.join('\n')}`);
}

function canonical(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
}
