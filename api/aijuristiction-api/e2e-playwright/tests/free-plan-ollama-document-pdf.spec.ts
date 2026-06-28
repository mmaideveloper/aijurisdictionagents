import { APIRequestContext, expect, test } from '@playwright/test';
import { execFile } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
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

const documentRequest =
  'Priprav mi splnomocnenie na prevadzku motoroveho vozidla firmy ESolutions SK s.r.o. ' +
  'pre Janka Hraska, bytom testova 10, Poprad, slovensko od 1.7.2026 na neurcito. ' +
  'Priprav document v slovenskom a anglickom jazyku.';

const liveTimeoutMs = Number(process.env.FREE_PLAN_DOCUMENT_E2E_TIMEOUT_MS ?? 300_000);

type CreatedUser = {
  user_id: string;
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

type ChatMessage = {
  role: string;
  content: string;
};

type DocumentExportOptions = {
  documents: {
    index: number;
    filename: string;
    title: string;
  }[];
};

test.beforeEach(async ({ request, baseURL }) => {
  await ensureLiveApiOrFail(request, baseURL);
});

test('free plan Ollama flow prepares clean Slovak and English splnomocnenie PDFs', async ({
  request,
  baseURL,
}) => {
  test.setTimeout(liveTimeoutMs);

  const runId = Date.now();
  const user = await createUser(request, baseURL, runId);
  const createdCase = await createCase(request, baseURL, user.user_id, `E2E free Ollama splnomocnenie ${runId}`);

  const route = await getEffectiveRoute(request, baseURL, user.user_id);
  expect(route).toMatchObject({
    plan_code: 'free',
    route_type: 'free_local',
    provider: 'local_ollama',
    model: 'qwen3:1.7b',
    is_local: true,
    is_external: false,
  });

  const session = await createSession(request, baseURL, user.user_id, createdCase.case_id);
  const assistantMessages: ChatMessage[] = [];

  assistantMessages.push(await sendReply(request, baseURL, session.id, documentRequest));
  expectConversationIsProfessional(assistantMessages);
  expectNoDuplicateAssistantQuestions(assistantMessages);

  const exports = await listDocumentExports(request, baseURL, session.id);
  if (exports.documents.length < 2) {
    assistantMessages.push(
      await sendReply(
        request,
        baseURL,
        session.id,
        'Na konci konverzacie teraz poziadam o PDF: vygeneruj prosim finalne PDF dokumenty v slovenskom aj anglickom jazyku.'
      )
    );
  }

  expectConversationIsProfessional(assistantMessages);
  expectNoDuplicateAssistantQuestions(assistantMessages);

  const readyExports = await listDocumentExports(request, baseURL, session.id);
  expect(readyExports.documents.length).toBeGreaterThanOrEqual(2);

  const pdfTexts = await Promise.all(
    readyExports.documents.slice(0, 2).map(async (document) => {
      const pdf = await request.get(`${baseURL}/v1/chat/sessions/${session.id}/export/documents/${document.index}`, {
        headers: { 'x-api-key': apiKey },
        timeout: liveTimeoutMs,
      });
      expect(pdf.status()).toBe(200);
      expect(pdf.headers()['content-type']).toContain('application/pdf');
      return extractPdfText(Buffer.from(await pdf.body()));
    })
  );

  const normalizedTexts = pdfTexts.map((text) => canonical(text));
  const combined = normalizedTexts.join('\n---document---\n');

  expect(combined).toContain('esolutions sk');
  expect(combined).toContain('janka hraska');
  expect(combined).toContain('testova 10');
  expect(combined).toContain('poprad');
  expect(combined).toContain('1.7.2026');

  expect(normalizedTexts.some((text) => text.includes('splnomocnenie'))).toBeTruthy();
  expect(normalizedTexts.some((text) => text.includes('power of attorney'))).toBeTruthy();

  for (const text of normalizedTexts) {
    expectLegalDocumentOnly(text);
  }
});

async function createUser(
  request: APIRequestContext,
  baseURL: string | undefined,
  runId: number
): Promise<CreatedUser> {
  const response = await request.post(`${baseURL}/v1/users/sign-up`, {
    headers: { 'x-api-key': apiKey },
    data: {
      phone_number: `+421902${String(runId).slice(-6)}`,
      email: `free-ollama-document-e2e.${runId}@example.test`,
      password: 'secret',
    },
  });
  expect(response.status()).toBe(201);
  return (await response.json()) as CreatedUser;
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

async function getEffectiveRoute(
  request: APIRequestContext,
  baseURL: string | undefined,
  userId: string
): Promise<EffectiveRoute> {
  const response = await request.get(`${baseURL}/v1/model-routing/effective?task_type=chat_reply&user_id=${userId}`, {
    headers: { 'x-api-key': apiKey },
  });
  expect(response.status()).toBe(200);
  return (await response.json()) as EffectiveRoute;
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
  expect(response.status()).toBe(200);
  const message = (await response.json()) as ChatMessage;
  expect(message.role).toBe('assistant');
  expect(
    message.content.trim().length,
    `Assistant reply should not be empty for prompt: ${content}`
  ).toBeGreaterThan(40);
  return message;
}

async function listDocumentExports(
  request: APIRequestContext,
  baseURL: string | undefined,
  sessionId: string
): Promise<DocumentExportOptions> {
  const response = await request.get(`${baseURL}/v1/chat/sessions/${sessionId}/export/documents`, {
    headers: { 'x-api-key': apiKey },
    timeout: liveTimeoutMs,
  });
  expect(response.status()).toBe(200);
  return (await response.json()) as DocumentExportOptions;
}

function expectConversationIsProfessional(messages: ChatMessage[]): void {
  for (const message of messages) {
    const visible = canonical(stripTechnicalPayload(message.content));
    expect(visible).not.toMatch(/connection error|internal_server_error|network|traceback|exception|undefined|null/);
    expect(visible).not.toMatch(/\bwtf\b|blbost|hlupost|idiot|stupid/);
    expect(visible).toMatch(/splnomocnen|dokument|pdf|prav|prosim|priprav|vozidl|attorney|document/);
  }
}

function expectNoDuplicateAssistantQuestions(messages: ChatMessage[]): void {
  const seen = new Set<string>();
  for (const message of messages) {
    for (const question of extractQuestions(stripTechnicalPayload(message.content))) {
      const normalized = canonical(question).replace(/[^a-z0-9 ]/g, '').replace(/\s+/g, ' ').trim();
      if (!normalized) {
        continue;
      }
      expect(seen.has(normalized), `Duplicate assistant question: ${question}`).toBeFalsy();
      seen.add(normalized);
    }
  }
}

function expectLegalDocumentOnly(text: string): void {
  expect(text).not.toMatch(/case_update_json|facts_summary|open_questions|client_goal/);
  expect(text).not.toMatch(/assistant|lawyerslovakia|jurisdigta assistant|system|user:/);
  expect(text).not.toMatch(/pripravil som|rozumiem|prosim doplnte|chybajuce informacie|zhrnutie pripadu/);
  expect(text).not.toMatch(/navrhovany postup|rizika|stiahnutie|ready for download|draft package/);
  expect(text).not.toMatch(/\*\*|---|```/);
}

function stripTechnicalPayload(content: string): string {
  return content.replace(/CASE_UPDATE_JSON\s*:?\s*[\s\S]*$/i, '').trim();
}

function extractQuestions(content: string): string[] {
  return content
    .split('?')
    .slice(0, -1)
    .map((part) => {
      const sentenceStart = Math.max(part.lastIndexOf('\n'), part.lastIndexOf('.'), part.lastIndexOf('!'));
      return `${part.slice(sentenceStart + 1).trim()}?`;
    })
    .filter((question) => question.length > 1);
}

async function extractPdfText(pdf: Buffer): Promise<string> {
  const tempDir = await mkdtemp(path.join(tmpdir(), 'jurisdigta-free-ollama-doc-'));
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
