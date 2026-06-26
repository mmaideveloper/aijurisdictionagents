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
  expect(pdfText).toContain('JurisDigta');
  expect(pdfText).not.toContain('Rozumiem');
  expect(pdfText).not.toContain('Zhrnutie');
  expect(pdfText).not.toContain('English version');
  expect(pdfText).not.toContain('hereby authorize');
  expect(pdfText).not.toContain('Technicke udaje');
  expect(pdfText).not.toContain('Prosim, doplnte');
  expect(pdfText).not.toContain('**');
  expect(pdfText).not.toContain('---');
});

test('case generated Slovak and English PDFs stay clean and language-separated', async ({
  request,
  baseURL,
}) => {
  const runId = Date.now();
  const user = await createUser(request, baseURL, runId);
  const createdCase = await createCase(request, baseURL, user.user_id, `E2E clean bilingual PDFs ${runId}`);
  const documents = await seedCleanBilingualGeneratedDocuments(createdCase.case_id, user.user_id);

  const slovakPdf = await request.get(
    `${baseURL}/v1/cases/${createdCase.case_id}/documents/${documents.slovakDocId}/pdf?user_id=${user.user_id}`,
    { headers: { 'x-api-key': apiKey } }
  );
  const englishPdf = await request.get(
    `${baseURL}/v1/cases/${createdCase.case_id}/documents/${documents.englishDocId}/pdf?user_id=${user.user_id}`,
    { headers: { 'x-api-key': apiKey } }
  );

  expect(slovakPdf.ok()).toBeTruthy();
  expect(englishPdf.ok()).toBeTruthy();
  expect(slovakPdf.headers()['content-type']).toContain('application/pdf');
  expect(englishPdf.headers()['content-type']).toContain('application/pdf');

  const slovakText = await extractPdfText(Buffer.from(await slovakPdf.body()));
  const englishText = await extractPdfText(Buffer.from(await englishPdf.body()));

  expect(slovakText).toContain('SPLNOMOCNENIE');
  expect(slovakText).toContain('tymto splnomocnujem');
  expect(slovakText).toContain('PP472DT');
  expect(slovakText).not.toContain('POWER OF ATTORNEY');
  expect(slovakText).not.toContain('hereby authorize');

  expect(englishText).toContain('POWER OF ATTORNEY');
  expect(englishText).toContain('hereby authorize');
  expect(englishText).toContain('PP472DT');
  expect(englishText).not.toContain('SPLNOMOCNENIE');
  expect(englishText).not.toContain('tymto splnomocnujem');

  for (const text of [slovakText, englishText]) {
    expect(text).toContain('JurisDigta');
    expect(text).not.toContain('Spracovanie stale prebieha');
    expect(text).not.toContain('LawyerSlovakia');
    expect(text).not.toContain('Ospravedlnujem');
    expect(text).not.toContain('Zhrnutie pripadu');
    expect(text).not.toContain('Chybajuce informacie');
    expect(text).not.toContain('Rizika');
    expect(text).not.toContain('Navrhovany postup');
    expect(text).not.toContain('export do PDF');
    expect(text).not.toContain('**');
    expect(text).not.toContain('---');
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

async function seedCleanBilingualGeneratedDocuments(
  caseId: string,
  userId: string
): Promise<{ slovakDocId: string; englishDocId: string }> {
  const script = String.raw`
import json
import os
from aijurisdictionagents.api_db import ApiDatabaseStore

case_id = os.environ["E2E_CASE_ID"]
user_id = os.environ["E2E_USER_ID"]
store = ApiDatabaseStore.from_env()
store.initialize()
slovak_doc_id = store.add_case_document(
    case_id=case_id,
    kind="generated_document",
    version=1,
    original_filename="splnomocnenie_sk.pdf",
    payload=(
        "SPLNOMOCNENIE\n\n"
        "Ja, RNDr. Marek Matonok, tymto splnomocnujem Emiliu Testovu na vsetky "
        "ukony suvisiace s pouzivanim firemneho vozidla PP472DT.\n\n"
        "Podpis: ________________________"
    ).encode("utf-8"),
    uploaded_by_user_id=user_id,
)
english_doc_id = store.add_case_document(
    case_id=case_id,
    kind="generated_document",
    version=2,
    original_filename="power_of_attorney_en.pdf",
    payload=(
        "POWER OF ATTORNEY\n\n"
        "I, RNDr. Marek Matonok, hereby authorize Emilia Testova to perform all acts "
        "related to the use of the company vehicle with registration number PP472DT.\n\n"
        "Signature: ________________________"
    ).encode("utf-8"),
    uploaded_by_user_id=user_id,
)
print(json.dumps({"slovakDocId": slovak_doc_id, "englishDocId": english_doc_id}))
`;
  return JSON.parse(
    await runPython(script, { E2E_CASE_ID: caseId, E2E_USER_ID: userId })
  ) as { slovakDocId: string; englishDocId: string };
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

  throw new Error(`No Python runtime was available for PDF e2e setup. Failures:\n${failures.join('\n')}`);
}
