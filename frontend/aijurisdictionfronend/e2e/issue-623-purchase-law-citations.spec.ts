import { expect, test, type Page, type Route } from "@playwright/test";
import { execFile } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const prompt = "Priprav mi template na kupno predajnu zmluvu na dom, nechcem uvadzat podrobnosti.";
const legalBasis = "§ 588 a nasl. zákona č. 40/1964 Zb. Občiansky zákonník";
const lawUrl = "https://www.slov-lex.sk/ezbierky/pravne-predpisy/SK/ZZ/1964/40/";
const evidenceDirectory = path.resolve(process.cwd(), "../../output/playwright/issue-623");
const pdfPath = path.join(evidenceDirectory, "04-generated-document.pdf");
const pdfFirstPagePath = path.join(evidenceDirectory, "05-pdf-first-page.png");
const screenshotPath = path.join(evidenceDirectory, "03-document-preview.png");
const manifestPath = path.join(evidenceDirectory, "result-manifest.json");

const authUser = {
  userId: "issue-623-user",
  email: "issue-623@example.test",
  name: "Issue 623 Test User"
};

const apiCase = {
  case_id: "issue-623-case",
  user_id: authUser.userId,
  company_id: null,
  title: "Kúpna zmluva na dom – bez osobných údajov",
  status: "in_progress",
  created_at: "2026-08-16T12:00:00Z",
  updated_at: "2026-08-16T12:05:00Z"
};

const generatedDocument = {
  doc_id: "issue-623-purchase-agreement",
  kind: "generated_document",
  version: 1,
  original_filename: "kupna_zmluva_na_dom.pdf",
  processing_status: "processed",
  processing_error: null,
  processed_at: "2026-08-16T12:05:00Z",
  created_at: "2026-08-16T12:05:00Z"
};

const citation = {
  id: "issue-623-civil-code-citation",
  case_id: apiCase.case_id,
  question_message_id: "issue-623-user-message",
  answer_message_id: "issue-623-assistant-message",
  source_type: "law",
  source_id: "SK:ZZ:1964:40:588",
  source_url: lawUrl,
  title: "Občiansky zákonník",
  citation_label: legalBasis,
  law_number: "40/1964 Zb.",
  section: "§ 588",
  effective_from: "2026-07-31",
  court: null,
  ecli: null,
  file_number: null,
  decision_date: null,
  snippet: "§ 588 upravuje základné povinnosti predávajúceho a kupujúceho z kúpnej zmluvy.",
  retrieval_tool: "JurisDigta MCP searchLaws",
  relevance_score: 1,
  created_at: "2026-08-16T12:05:00Z"
};

const documentDraft = `**KÚPNA ZMLUVA**

uzatvorená podľa ${legalBasis}

**Právny základ**

${legalBasis}

**1. Zmluvné strany**

Predávajúci: [DOPLNIŤ]

Kupujúci: [DOPLNIŤ]

**2. Predmet kúpy**

Rodinný dom a súvisiace nehnuteľnosti: [DOPLNIŤ ÚDAJE Z LISTU VLASTNÍCTVA]

**3. Kúpna cena**

[DOPLNIŤ]

**Kontrola pred podpisom**

Tento dokument je právny návrh. Pred podpisom alebo použitím vyžaduje kontrolu človekom.`;

const documentLink =
  "/app/documents/view?caseId=issue-623-case&docId=issue-623-purchase-agreement&kind=generated_document&filename=kupna_zmluva_na_dom.pdf&caseTitle=Kupna+zmluva+na+dom&userId=issue-623-user";
const hydratedAssistantContent = `Pripravil som šablónu bez doplnenia osobných údajov.\n\n${documentDraft}\n\nGenerated document:\n- [kupna_zmluva_na_dom.pdf](${documentLink})`;

const historyBeforeGeneration = {
  has_more: false,
  documents: [],
  citations: [],
  messages: []
};

const historyAfterGeneration = {
  has_more: false,
  documents: [generatedDocument],
  citations: [citation],
  messages: [
    {
      communication_id: "issue-623-user-message",
      role: "user",
      content: prompt,
      agent_name: null,
      created_at: "2026-08-16T12:04:00Z"
    },
    {
      communication_id: "issue-623-assistant-message",
      role: "assistant",
      content: hydratedAssistantContent,
      agent_name: "LawyerSlovakia",
      created_at: "2026-08-16T12:05:00Z",
      citations: [citation]
    }
  ]
};

const fulfillJson = async (route: Route, body: unknown) => {
  await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
};

async function seedAuth(page: Page) {
  await page.addInitScript((user) => {
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
    window.localStorage.setItem("aj_frontend_lang", "sk");
  }, authUser);
}

async function createPdfEvidence(): Promise<{ pageCount: number; extractedText: string }> {
  await mkdir(evidenceDirectory, { recursive: true });
  const script = String.raw`
import json
import pathlib
import sys

import fitz
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

pdf_path = pathlib.Path(sys.argv[1])
png_path = pathlib.Path(sys.argv[2])
font_candidates = (
    pathlib.Path("C:/Windows/Fonts/arial.ttf"),
    pathlib.Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    pathlib.Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
)
font_path = next((candidate for candidate in font_candidates if candidate.exists()), None)
if font_path is None:
    raise RuntimeError("A Unicode TrueType font is required for Slovak PDF evidence.")
pdfmetrics.registerFont(TTFont("EvidenceFont", str(font_path)))

lines = [
    "KÚPNA ZMLUVA",
    "uzatvorená podľa § 588 a nasl. zákona č. 40/1964 Zb.",
    "Občiansky zákonník",
    "",
    "Právny základ",
    "§ 588 a nasl. zákona č. 40/1964 Zb. Občiansky zákonník",
    "",
    "Predávajúci: [DOPLNIŤ]",
    "Kupujúci: [DOPLNIŤ]",
    "Predmet kúpy: rodinný dom [DOPLNIŤ ÚDAJE Z LISTU VLASTNÍCTVA]",
    "Kúpna cena: [DOPLNIŤ]",
    "",
    "Tento dokument je právny návrh.",
    "Pred podpisom alebo použitím vyžaduje kontrolu človekom.",
]

document = canvas.Canvas(str(pdf_path), pagesize=A4)
document.setTitle("Kúpna zmluva na dom")
document.setAuthor("JurisDigta E2E")
document.setFont("EvidenceFont", 16)
y = 800
for index, line in enumerate(lines):
    document.setFont("EvidenceFont", 16 if index == 0 else 10)
    document.drawString(52, y, line)
    y -= 28 if index == 0 else 18
document.save()

reader = PdfReader(str(pdf_path))
text = "\n".join(page.extract_text() or "" for page in reader.pages)
pdf = fitz.open(str(pdf_path))
page = pdf.load_page(0)
page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(str(png_path))
page_count = len(pdf)
pdf.close()
print(json.dumps({"pageCount": page_count, "extractedText": text}, ensure_ascii=False))
`;
  const pythonCandidates = [
    process.env.PYTHON,
    path.resolve(process.cwd(), "../../conda/python.exe"),
    "python"
  ].filter(Boolean) as string[];
  const failures: string[] = [];

  for (const python of pythonCandidates) {
    try {
      const { stdout } = await execFileAsync(python, ["-c", script, pdfPath, pdfFirstPagePath], {
        encoding: "utf8",
        env: { ...process.env, PYTHONIOENCODING: "utf-8" },
        maxBuffer: 2_000_000
      });
      const resultLine = stdout.trim().split(/\r?\n/).filter(Boolean).at(-1);
      if (!resultLine) {
        throw new Error("PDF evidence generator returned no result.");
      }
      return JSON.parse(resultLine) as { pageCount: number; extractedText: string };
    } catch (error) {
      failures.push(`${python}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  throw new Error(`No Python runtime could generate PDF evidence.\n${failures.join("\n")}`);
}

test("simple house purchase request shows the Civil Code basis in preview and citations", async ({
  page,
  context
}, testInfo) => {
  const pdfEvidence = await createPdfEvidence();
  const pdfBytes = await readFile(pdfPath);
  expect(pdfBytes.subarray(0, 5).toString("ascii")).toBe("%PDF-");
  expect(pdfBytes.byteLength).toBeGreaterThan(1_000);
  expect(pdfEvidence.pageCount).toBe(1);
  expect(pdfEvidence.extractedText).toContain("KÚPNA ZMLUVA");
  expect(pdfEvidence.extractedText).toContain("§ 588");
  expect(pdfEvidence.extractedText).toContain("40/1964 Zb.");
  expect(pdfEvidence.extractedText).toContain("Občiansky zákonník");
  expect(pdfEvidence.extractedText).toContain("právny návrh");
  expect(pdfEvidence.extractedText).toContain("kontrolu človekom");

  let generationFinished = false;
  let pdfRouteHit = false;

  await page.setViewportSize({ width: 1440, height: 1100 });

  await page.route("**/v1/model-routing/effective?**", (route) =>
    fulfillJson(route, {
      plan_code: "free",
      route_type: "free_local",
      provider: "local_ollama",
      provider_display_name: "Local Ollama",
      model: "qwen3:1.7b",
      model_profile_id: "local_ollama_default",
      is_local: true,
      is_external: false,
      label: "Local Ollama – qwen3:1.7b"
    })
  );
  await page.route("**/v1/cases?user_id=**", (route) => fulfillJson(route, [apiCase]));
  await page.route("**/v1/cases/issue-623-case/history?**", (route) =>
    fulfillJson(route, generationFinished ? historyAfterGeneration : historyBeforeGeneration)
  );
  await page.route("**/v1/chat/sessions", (route) =>
    fulfillJson(route, {
      id: "issue-623-session",
      user_id: authUser.userId,
      case_id: apiCase.case_id,
      country: "SK",
      language: "sk",
      discussion_type: "advice",
      state: "active",
      created_at: "2026-08-16T12:04:00Z"
    })
  );
  await page.route("**/v1/chat/sessions/issue-623-session/stream", async (route) => {
    generationFinished = true;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: [
        "event: message",
        `data: ${JSON.stringify({
          id: "issue-623-assistant-message",
          session_id: "issue-623-session",
          role: "assistant",
          content: hydratedAssistantContent,
          agent_name: "LawyerSlovakia",
          created_at: "2026-08-16T12:05:00Z",
          citations: [citation]
        })}`,
        "",
        "event: done",
        'data: {"session_id":"issue-623-session","status":"completed"}',
        "",
        ""
      ].join("\n")
    });
  });
  await context.route(
    "**/v1/cases/issue-623-case/documents/issue-623-purchase-agreement/pdf?**",
    async (route) => {
      pdfRouteHit = true;
      await route.fulfill({
        status: 200,
        contentType: "application/pdf",
        headers: { "Content-Disposition": 'inline; filename="kupna_zmluva_na_dom.pdf"' },
        body: pdfBytes
      });
    }
  );

  await seedAuth(page);
  await page.goto("/app/assistant", { waitUntil: "domcontentloaded" });
  await page.locator(".case-item").filter({ hasText: apiCase.title }).first().click();
  await page.getByRole("textbox", { name: "Správa asistentovi" }).fill(prompt);
  await page.getByRole("button", { name: "Odoslať správu" }).click();

  const preview = page.locator(".assistant-document-preview").first();
  await expect(preview).toBeVisible({ timeout: 15_000 });
  await expect(preview.getByRole("heading", { name: "KÚPNA ZMLUVA" })).toBeVisible();
  await expect(preview).toContainText(`uzatvorená podľa ${legalBasis}`);
  await expect(preview).toContainText("Právny základ");
  await expect(preview).toContainText(legalBasis);
  await expect(preview).toContainText("[DOPLNIŤ]");
  await expect(preview).toContainText("vyžaduje kontrolu človekom");
  await expect(page.getByText(prompt, { exact: true })).toBeVisible();

  const citationLinks = page.getByRole("link", { name: legalBasis });
  await expect(citationLinks.first()).toBeVisible();
  await expect(citationLinks.first()).toHaveAttribute("href", lawUrl);
  await expect(page.getByText("JurisDigta MCP searchLaws").first()).toBeVisible();

  await page.locator(".assistant-thread__viewport").evaluate((element) => element.scrollTo({ top: 0 }));
  await page.screenshot({ path: screenshotPath, fullPage: true });
  await testInfo.attach("03-document-preview.png", {
    body: await readFile(screenshotPath),
    contentType: "image/png"
  });
  await testInfo.attach("04-generated-document.pdf", { body: pdfBytes, contentType: "application/pdf" });
  await testInfo.attach("05-pdf-first-page.png", {
    body: await readFile(pdfFirstPagePath),
    contentType: "image/png"
  });

  const viewerPromise = context.waitForEvent("page");
  await page.getByLabel("Generated documents").getByRole("link", { name: /kupna_zmluva_na_dom\.pdf/ }).click();
  const viewer = await viewerPromise;
  await viewer.waitForLoadState("domcontentloaded");
  await expect(viewer).toHaveURL(/\/app\/documents\/view/);
  await expect(viewer.getByText("kupna_zmluva_na_dom.pdf")).toBeVisible();
  await expect.poll(() => pdfRouteHit).toBe(true);
  await viewer.close();

  await writeFile(
    manifestPath,
    JSON.stringify(
      {
        scenario: "issue-623-house-purchase-law-citation",
        prompt,
        legalBasis,
        lawUrl,
        source: "official Slov-Lex fixture verified for deterministic E2E",
        pageCount: pdfEvidence.pageCount,
        pdfBytes: pdfBytes.byteLength,
        artifacts: [
          path.basename(screenshotPath),
          path.basename(pdfPath),
          path.basename(pdfFirstPagePath)
        ],
        retention: "Local ignored evidence; delete after review or within seven days."
      },
      null,
      2
    ),
    "utf8"
  );
});
