import { APIRequestContext, expect, test } from '@playwright/test';
import { execFile } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';
import { ensureLiveApiOrFail } from './helpers/liveApi';

const execFileAsync = promisify(execFile);
const apiKey = process.env.API_KEY ?? 'aijuris';

type CreatedUser = {
  user_id: string;
};

type CreatedCase = {
  case_id: string;
};

test.beforeEach(async ({ request, baseURL }) => {
  await ensureLiveApiOrFail(request, baseURL);
});

test('case generated PDF renders selected Slovak document without assistant or English blocks', async ({
  request,
  baseURL,
}) => {
  const runId = Date.now();
  const user = await createUser(request, baseURL, runId);
  const createdCase = await createCase(request, baseURL, user.user_id, `E2E splnomocnenie ${runId}`);
  const docId = await seedContaminatedLinkedDocument(createdCase.case_id, user.user_id);

  const pdf = await request.get(
    `${baseURL}/v1/cases/${createdCase.case_id}/documents/${docId}/pdf?user_id=${user.user_id}`,
    { headers: { 'x-api-key': apiKey } }
  );

  expect(pdf.ok()).toBeTruthy();
  expect(pdf.headers()['content-type']).toContain('application/pdf');
  const pdfText = await extractPdfText(Buffer.from(await pdf.body()));
  expect(pdfText).toContain('Splnomocnenie');
  expect(pdfText).toContain('Splnomocnenie (Slovenska verzia)');
  expect(pdfText).toContain('Jan Novak');
  expect(pdfText).toContain('tymto splnomocnujem');
  expect(pdfText).toContain('JurisDicta');
  expect(pdfText).not.toContain('Rozumiem');
  expect(pdfText).not.toContain('Zhrnutie');
  expect(pdfText).not.toContain('English version');
  expect(pdfText).not.toContain('hereby authorize');
  expect(pdfText).not.toContain('Technicke udaje');
  expect(pdfText).not.toContain('Prosim, doplnte');
  expect(pdfText).not.toContain('**');
  expect(pdfText).not.toContain('---');
});

async function createUser(
  request: APIRequestContext,
  baseURL: string | undefined,
  runId: number
): Promise<CreatedUser> {
  const response = await request.post(`${baseURL}/v1/users/sign-up`, {
    headers: { 'x-api-key': apiKey },
    data: {
      phone_number: `+421901${String(runId).slice(-6)}`,
      email: `case-pdf-e2e.${runId}@example.test`,
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

async function seedContaminatedLinkedDocument(caseId: string, userId: string): Promise<string> {
  const script = String.raw`
import os
from aijurisdictionagents.api_db import ApiDatabaseStore

case_id = os.environ["E2E_CASE_ID"]
user_id = os.environ["E2E_USER_ID"]
store = ApiDatabaseStore.from_env()
store.initialize()
doc_id = store.add_case_text_document(
    case_id=case_id,
    original_filename="assistant-technical.json",
    content='{"case":{"status":"document_ready"}}',
    uploaded_by_user_id=user_id,
)
content = (
    "Rozumiem, pripravim dokument.\n\n"
    "Zhrnutie:\n"
    "- dokument bude slovensky\n\n"
    "---\n\n"
    "**Splnomocnenie (Slovenska verzia)**\n\n"
    "Ja, Jan Novak, tymto splnomocnujem Mariu Mrkvickovu na zastupovanie.\n\n"
    "Datum: 25. juna 2026\n\n"
    "Podpis: ________________________\n\n"
    "---\n\n"
    "**Splnomocnenie (English version)**\n\n"
    "I, Jan Novak, hereby authorize Maria Mrkvickova to represent me in all legal "
    "and administrative actions related to the matter, including receiving documents "
    "and signing procedural submissions on my behalf.\n\n"
    "Datum: June 25, 2026\n\n"
    "Podpis: ________________________\n\n"
    "---\n\n"
    f"Technicke udaje som ulozil do dokumentu pripadu: /v1/cases/{case_id}/documents/{doc_id}?user_id={user_id}\n\n"
    "Prosim, doplnte dalsie udaje, ak chcete dokument rozsirit."
)
store.add_case_message(
    case_id=case_id,
    role="assistant",
    content=content,
    agent_name="LawyerSlovakia",
)
print(doc_id)
`;
  return (await runPython(script, { E2E_CASE_ID: caseId, E2E_USER_ID: userId })).trim();
}

async function extractPdfText(pdf: Buffer): Promise<string> {
  const tempDir = await mkdtemp(path.join(tmpdir(), 'jurisdigta-e2e-pdf-'));
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
  let lastError = '';

  for (const candidate of candidates) {
    try {
      const { stdout } = await execFileAsync(candidate, ['-c', script, ...args], {
        encoding: 'utf8',
        env: {
          ...process.env,
          ...extraEnv,
          PYTHONIOENCODING: 'utf-8',
        },
        maxBuffer: 2_000_000,
      });
      return stdout;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
  }

  throw new Error(`No Python runtime was available for PDF e2e setup. Last error: ${lastError}`);
}
