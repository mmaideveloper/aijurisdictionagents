import { readFile, writeFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

const authUser = {
  userId: "user-e2e",
  email: "readiness@example.test",
  name: "Synthetic Tester"
};

const apiCase = {
  case_id: "case-generated-doc",
  user_id: authUser.userId,
  company_id: null,
  title: "test generated document",
  status: "in_progress",
  created_at: "2026-06-26T10:00:00Z",
  updated_at: "2026-06-26T10:05:00Z"
};

const generatedDocument = {
  doc_id: "doc-generated-splnomocnenie",
  kind: "generated_document",
  version: 1,
  original_filename: "splnomocnenie_ESolutions_SK.pdf",
  processing_status: "processed",
  processing_error: null,
  processed_at: "2026-06-26T10:05:00Z",
  created_at: "2026-06-26T10:05:00Z"
};

test.afterEach(async ({ page }, testInfo) => {
  if (!page.isClosed()) await page.screenshot({ path: testInfo.outputPath("03-final-state.png"), fullPage: true });
});

test.beforeEach(async ({ page }) => {
  await page.route("**/v1/cases?user_id=**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([apiCase])
    });
  });

  await page.route("**/v1/cases/case-generated-doc/history?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        has_more: false,
        documents: [generatedDocument],
        messages: [
          {
            communication_id: "msg-user-1",
            role: "user",
            content: "ano",
            agent_name: null,
            created_at: "2026-06-26T10:04:00Z"
          },
          {
            communication_id: "msg-assistant-1",
            role: "assistant",
            content:
              "USER-FACING: Splnomocnenie bolo úspešne pripravené a je pripravené na stiahnutie.\n\n" +
              "Môžete si ho stiahnuť pomocou nasledujúceho odkazu:\n\n" +
              "[Stiahnuť splnomocnenie](documents/splnomocnenie_ESolutions_SK.pdf)",
            agent_name: "LawyerSlovakia",
            created_at: "2026-06-26T10:05:00Z"
          }
        ]
      })
    });
  });

  await page.addInitScript((user) => {
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
    window.localStorage.setItem("aj_frontend_lang", "en");
  }, authUser);
});

test("generated documents are downloadable and listed for the selected case", async ({ page }) => {
  const casesResponse = page.waitForResponse((response) =>
    response.url().includes("/v1/cases?user_id=user-e2e") && response.status() === 200
  );
  const historyResponse = page.waitForResponse((response) =>
    response.url().includes("/v1/cases/case-generated-doc/history") && response.status() === 200
  );

  await page.goto("/app/assistant", { waitUntil: "domcontentloaded" });
  await casesResponse;
  await historyResponse;

  const caseButton = page.locator(".case-item").filter({ hasText: "test generated document" });
  await expect(caseButton).toBeVisible();
  await caseButton.click();

  await expect(page.getByRole("heading", { name: /dokumenty|documents/i })).toBeVisible();
  const generatedFilename = "splnomocnenie_ESolutions_SK.pdf";
  const sidebarDocumentItem = page.locator(".sidebar-document-item").filter({
    has: page.locator(".sidebar-document-link", { hasText: generatedFilename })
  });
  const sidebarDocumentLink = sidebarDocumentItem.locator("button.sidebar-document-link");
  const sidebarDeleteButton = sidebarDocumentItem.getByRole("button", {
    name: `Delete document ${generatedFilename}`,
    exact: true
  });

  await expect(sidebarDocumentItem).toHaveCount(1);
  await expect(sidebarDocumentLink).toHaveCount(1);
  await expect(sidebarDocumentLink).toBeVisible();
  await expect(sidebarDeleteButton).toBeVisible();

  const documentActions = page.getByLabel("Generated documents");
  await expect(documentActions.getByRole("link", { name: /splnomocnenie_ESolutions_SK\.pdf/i })).toBeVisible();
  await expect(
    documentActions.getByRole("link", { name: /splnomocnenie_ESolutions_SK\.pdf/i })
  ).toHaveAttribute(
    "href",
    /\/app\/documents\/view\?caseId=case-generated-doc&docId=doc-generated-splnomocnenie/
  );

  await expect(page.locator(".assistant-thread__viewport")).not.toContainText("documents/splnomocnenie_ESolutions_SK.pdf");
  await expect(page.locator(".assistant-thread__viewport")).not.toContainText("Stiahnuť splnomocnenie");
});


test("confirmed draft without storage does not claim export success or expose PDF links", async ({ page }) => {
  await page.route("**/v1/cases/case-generated-doc/history?**", async (route) => {
    await route.fulfill({ json: {
      has_more: false, documents: [], messages: [
        { communication_id: "confirmed", role: "user", content: "ano", created_at: "2026-06-26T10:04:00Z" },
        { communication_id: "false-ready", role: "assistant", agent_name: "Assistant",
          content: "Dokument je pripravený na stiahnutie. [Download PDF](/app/documents/view?caseId=case-generated-doc&docId=invented)",
          created_at: "2026-06-26T10:05:00Z" }
      ]
    } });
  });
  await page.goto("/app/assistant");
  await page.locator(".case-item").filter({ hasText: "test generated document" }).click();
  await expect(page.getByText("The document is not ready for download.", { exact: false })).toBeVisible();
  await expect(page.locator(".assistant-thread__viewport")).not.toContainText("pripravený na stiahnutie");
  await expect(page.getByLabel("Generated documents")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Retry document generation", exact: true })).toBeVisible();
});

const fixturePdf = Buffer.from("JVBERi0xLjMKJZOMi54gUmVwb3J0TGFiIEdlbmVyYXRlZCBQREYgZG9jdW1lbnQgKG9wZW5zb3VyY2UpCjEgMCBvYmoKPDwKL0YxIDIgMCBSCj4+CmVuZG9iagoyIDAgb2JqCjw8Ci9CYXNlRm9udCAvSGVsdmV0aWNhIC9FbmNvZGluZyAvV2luQW5zaUVuY29kaW5nIC9OYW1lIC9GMSAvU3VidHlwZSAvVHlwZTEgL1R5cGUgL0ZvbnQKPj4KZW5kb2JqCjMgMCBvYmoKPDwKL0NvbnRlbnRzIDcgMCBSIC9NZWRpYUJveCBbIDAgMCA1OTUuMjc1NiA4NDEuODg5OCBdIC9QYXJlbnQgNiAwIFIgL1Jlc291cmNlcyA8PAovRm9udCAxIDAgUiAvUHJvY1NldCBbIC9QREYgL1RleHQgL0ltYWdlQiAvSW1hZ2VDIC9JbWFnZUkgXQo+PiAvUm90YXRlIDAgL1RyYW5zIDw8Cgo+PiAKICAvVHlwZSAvUGFnZQo+PgplbmRvYmoKNCAwIG9iago8PAovUGFnZU1vZGUgL1VzZU5vbmUgL1BhZ2VzIDYgMCBSIC9UeXBlIC9DYXRhbG9nCj4+CmVuZG9iago1IDAgb2JqCjw8Ci9BdXRob3IgKGFub255bW91cykgL0NyZWF0aW9uRGF0ZSAoRDoyMDI2MDkyNDExNTQxNyswMicwMCcpIC9DcmVhdG9yIChhbm9ueW1vdXMpIC9LZXl3b3JkcyAoKSAvTW9kRGF0ZSAoRDoyMDI2MDkyNDExNTQxNyswMicwMCcpIC9Qcm9kdWNlciAoUmVwb3J0TGFiIFBERiBMaWJyYXJ5IC0gXChvcGVuc291cmNlXCkpIAogIC9TdWJqZWN0ICh1bnNwZWNpZmllZCkgL1RpdGxlICh1bnRpdGxlZCkgL1RyYXBwZWQgL0ZhbHNlCj4+CmVuZG9iago2IDAgb2JqCjw8Ci9Db3VudCAxIC9LaWRzIFsgMyAwIFIgXSAvVHlwZSAvUGFnZXMKPj4KZW5kb2JqCjcgMCBvYmoKPDwKL0ZpbHRlciBbIC9BU0NJSTg1RGVjb2RlIC9GbGF0ZURlY29kZSBdIC9MZW5ndGggMTMyCj4+CnN0cmVhbQpHYXBRaDBFPUYsMFVcSDNUXHBOWVReUUtrP3RjPklQLDtXI1UxXjIzaWhQRU1fP0NXNEtJU2k8IVs3YCNPQl9zS2k2Jl1xTjc9JDdBOy05R2pPMmk1XUZvcG1lQVJUcV1bWXFNS3NdJ11QMSQoKDluZVpbS2IsaHQrVVZIU1ojOlg0fj5lbmRzdHJlYW0KZW5kb2JqCnhyZWYKMCA4CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDA2MSAwMDAwMCBuIAowMDAwMDAwMDkyIDAwMDAwIG4gCjAwMDAwMDAxOTkgMDAwMDAgbiAKMDAwMDAwMDQwMiAwMDAwMCBuIAowMDAwMDAwNDcwIDAwMDAwIG4gCjAwMDAwMDA3MzEgMDAwMDAgbiAKMDAwMDAwMDc5MCAwMDAwMCBuIAp0cmFpbGVyCjw8Ci9JRCAKWzxmNGYzN2NjYjMzZDIyZTAxMzI5OTk2NmEzY2ZlMDhkMj48ZjRmMzdjY2IzM2QyMmUwMTMyOTk5NjZhM2NmZTA4ZDI+XQolIFJlcG9ydExhYiBnZW5lcmF0ZWQgUERGIGRvY3VtZW50IC0tIGRpZ2VzdCAob3BlbnNvdXJjZSkKCi9JbmZvIDUgMCBSCi9Sb290IDQgMCBSCi9TaXplIDgKPj4Kc3RhcnR4cmVmCjEwMTIKJSVFT0YK", "base64");

test("saved document opens in viewer and downloads a nonempty PDF", async ({ page, context }) => {
  await context.route("**/v1/cases/case-generated-doc/documents/doc-generated-splnomocnenie**", async (route) => {
    const pdf = new URL(route.request().url()).pathname.endsWith("/pdf");
    await route.fulfill({ contentType: pdf ? "application/pdf" : "text/plain",
      body: pdf ? fixturePdf : "Synthetic document readiness fixture" });
  });
  await page.goto("/app/assistant");
  await page.locator(".case-item").filter({ hasText: "test generated document" }).click();
  const documentLink = page.getByLabel("Generated documents").getByRole("link").first();
  await expect(documentLink).toBeVisible();
  const popup = page.waitForEvent("popup");
  await documentLink.click();
  const viewer = await popup;
  await expect(viewer.locator(".document-viewer-page")).toBeVisible();
  const save = viewer.getByRole("button", { name: /save|download/i }).first();
  await expect(save).toBeEnabled();
  const downloadEvent = viewer.waitForEvent("download");
  await save.click();
  const download = await downloadEvent;
  const path = await download.path();
  expect(path).not.toBeNull();
  const bytes = await readFile(path!);
  expect(bytes.equals(fixturePdf)).toBeTruthy();
  expect(bytes.subarray(0, 5).toString()).toBe("%PDF-");
});

for (const status of [403, 404, 409]) {
  test(`viewer failure ${status} cannot offer a PDF download`, async ({ page }) => {
    await page.route("**/v1/cases/case-generated-doc/documents/missing**", (route) =>
      route.fulfill({ status, json: { detail: `Document unavailable (${status})` } })
    );
    await page.goto("/app/documents/view?caseId=case-generated-doc&docId=missing&kind=generated_document&filename=test.pdf&userId=user-e2e");
    await expect(page.getByText(`Document unavailable (${status})`, { exact: false })).toBeVisible();
    await expect(page.getByRole("button", { name: /save|download/i }).first()).toBeDisabled();
  });
}

test("storage error is actionable and retry exposes only the subsequently saved document", async ({ page }) => {
  let attempts = 0;
  await page.route("**/v1/cases/case-generated-doc/history?**", (route) => route.fulfill({ json: {
    has_more: false,
    documents: attempts >= 2 ? [generatedDocument] : [],
    messages: attempts >= 2 ? [{
      communication_id: "saved", role: "assistant", agent_name: "Assistant",
      content: "The document is ready for download.", created_at: "2026-06-26T10:05:00Z"
    }] : []
  } }));
  await page.route("**/v1/chat/sessions", (route) => route.fulfill({ json: {
    id: "retry-835", user_id: authUser.userId, case_id: apiCase.case_id,
    country: "SK", language: "en", discussion_type: "advice", state: "active",
    created_at: "2026-06-26T10:04:00Z"
  } }));
  await page.route("**/v1/chat/sessions/retry-835/stream", async (route) => {
    attempts += 1;
    const events = attempts === 1
      ? 'event: error\ndata: {"code":"document_generation_failed","message":"The document could not be saved. Please retry document generation."}\n\n'
      : 'event: message\ndata: {"id":"saved","session_id":"retry-835","role":"assistant","content":"The document is ready for download."}\n\nevent: done\ndata: {"session_id":"retry-835"}\n\n';
    await route.fulfill({ contentType: "text/event-stream", body: events });
  });
  await page.goto("/app/assistant");
  await page.locator(".case-item").filter({ hasText: apiCase.title }).click();
  await page.getByLabel("Assistant message").fill("Generate the confirmed PDF document.");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.getByText("The document could not be saved.", { exact: false })).toBeVisible();
  await expect(page.getByLabel("Generated documents")).toHaveCount(0);
  await page.getByRole("button", { name: "Retry document generation", exact: true }).click();
  await expect(page.getByLabel("Generated documents").getByRole("link")).toBeVisible();
  expect(attempts).toBe(2);
});


test("saved placeholder in history is not offered as a ready document", async ({ page }) => {
  await page.route("**/v1/cases/case-generated-doc/history?**", route => route.fulfill({ json: {
    has_more: false,
    documents: [{ ...generatedDocument, download_available: false }],
    messages: [{ communication_id: "legacy-placeholder", role: "assistant", agent_name: "Assistant",
      content: "Document is ready for download.", created_at: "2026-06-26T10:05:00Z" }]
  } }));
  await page.goto("/app/assistant");
  await page.locator(".case-item").filter({ hasText: apiCase.title }).click();
  await expect(page.getByText("The document is not ready for download.", { exact: false })).toBeVisible();
  await expect(page.getByLabel("Generated documents")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Retry document generation", exact: true })).toBeVisible();
});


for (const href of ["#", "/", "https://agent.jurisdigta.eu/app/assistant#", "/app/documents/view?caseId=case-generated-doc&docId=missing"]) {
  test(`placeholder download link ${href} shows retry instead of opening login`, async ({ page, context }) => {
    await page.route("**/v1/cases/case-generated-doc/history?**", route => route.fulfill({ json: {
      has_more: false, documents: [], messages: [{
        communication_id: "placeholder-link", role: "assistant", agent_name: "Assistant",
        content: `[Stiahnuť pracovnú zmluvu](${href})`, created_at: "2026-06-26T10:05:00Z"
      }]
    } }));
    await page.goto("/app/assistant");
    await page.locator(".case-item").filter({ hasText: apiCase.title }).click();
    await expect(page.getByText("The document is not ready for download.", { exact: false })).toBeVisible();
    await expect(page.getByRole("link", { name: "Stiahnuť pracovnú zmluvu" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Retry document generation", exact: true })).toBeVisible();
    await expect(page).toHaveURL(/\/app\/assistant$/);
    expect(context.pages()).toHaveLength(1);
  });
}

const structuredAction = (href: string) => ({
  schema_version: 1, renderer_id: "action_link", renderer_version: 1,
  data: { href, label: "Stiahnuť pracovnú zmluvu" }, fallback_text: "Document action",
  citations: [], notices: [], selection: {
    policy_id: "synthetic-835", reason_code: "validated", explicit_user_request: false, model_proposal_accepted: true
  }
});

for (const [name, href, documents] of [
  ["placeholder", "/app/assistant#", []],
  ["external PDF", "https://example.test/invented.pdf", []],
  ["missing ID", "/app/documents/view?caseId=case-generated-doc&docId=missing", []],
  ["other case", "/app/documents/view?caseId=other&docId=doc-generated-splnomocnenie", [generatedDocument]],
  ["unavailable content", "/app/documents/view?caseId=case-generated-doc&docId=doc-generated-splnomocnenie", [{ ...generatedDocument, download_available: false }]]
] as const) {
  test(`structured download rejects ${name}`, async ({ page, context }) => {
    await page.route("**/v1/cases/case-generated-doc/history?**", route => route.fulfill({ json: {
      has_more: false, documents, messages: [{
        communication_id: "structured-link", role: "assistant", agent_name: "Assistant",
        content: "Document action", presentation: structuredAction(href), created_at: "2026-06-26T10:05:00Z"
      }]
    } }));
    await page.goto("/app/assistant");
    await page.locator(".case-item").filter({ hasText: apiCase.title }).click();
    const block = page.locator('[data-renderer="action_link"]');
    await expect(block.getByRole("link")).toHaveCount(0);
    await expect(block.getByRole("status")).toContainText("The document is not ready for download.");
    await expect(block.getByRole("button", { name: "Retry document generation" })).toBeVisible();
    await expect(page).toHaveURL(/\/app\/assistant$/);
    expect(context.pages()).toHaveLength(1);
  });
}

const contractLines = [
  "Pracovna zmluva", "Zamestnavatel: Synthetic Firma", "Zamestnanec: Synthetic Osoba",
  "Druh prace: Vyvoj softveru", "Miesto vykonu prace: Kosice", "Nastup: 1. oktobra 2026",
  "Mesacna mzda: 3 200 EUR brutto", "Pracovny cas: 40 hodin tyzdenne",
  "Pracovny pomer na dobu neurcitu", "Podpis zamestnanca: __________",
  "Draft for human review before signing."
];

// Deterministic transport fixture, not evidence of real backend generation.
function contractPdf(): Buffer {
  const stream = `BT /F1 12 Tf 50 790 Td 22 TL\n${contractLines.map(line => `(${line}) Tj T*`).join("\n")}\nET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`
  ];
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, index) => { offsets.push(Buffer.byteLength(pdf)); pdf += `${index + 1} 0 obj\n${object}\nendobj\n`; });
  const xref = Buffer.byteLength(pdf);
  pdf += `xref\n0 6\n0000000000 65535 f \n${offsets.slice(1).map(offset => `${String(offset).padStart(10, "0")} 00000 n `).join("\n")}\ntrailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(pdf);
}

for (const failFirst of [false, true]) {
  test(`employment draft confirmation reaches structured viewer and PDF${failFirst ? " after storage retry" : ""}`, async ({ page }, testInfo) => {
    let attempts = 0;
    let saved = false;
    const href = "/app/documents/view?caseId=case-generated-doc&docId=doc-generated-splnomocnenie&kind=generated_document&filename=employment.pdf&userId=user-e2e";
    const message = () => ({
      communication_id: saved ? "stored" : "draft", role: "assistant", agent_name: "Assistant",
      content: saved ? "Document action" : `${contractLines.join("\n")}\n\nMam pripravit tento dokument vo formate PDF?`,
      ...(saved ? { presentation: structuredAction(href) } : {}), created_at: "2026-06-26T10:05:00Z"
    });
    await page.route("**/v1/cases/case-generated-doc/history?**", route => route.fulfill({ json: {
      has_more: false, documents: saved ? [{ ...generatedDocument, original_filename: "employment.pdf", download_available: true }] : [],
      messages: [message()]
    } }));
    await page.route("**/v1/chat/sessions", route => route.fulfill({ json: {
      id: "employment-835", user_id: authUser.userId, case_id: apiCase.case_id, country: "SK", language: "en",
      discussion_type: "advice", state: "active", created_at: "2026-06-26T10:04:00Z"
    } }));
    await page.route("**/v1/chat/sessions/employment-835/stream", route => {
      attempts += 1;
      const request = route.request().postDataJSON();
      expect(request.instruction).toBeTruthy();
      if (attempts === 1) expect(request.instruction).toBe("dobre");
      saved = !failFirst || attempts > 1;
      const events = saved
        ? `event: message\ndata: ${JSON.stringify({ ...message(), id: "stored", session_id: "employment-835", generated_document_ids: [generatedDocument.doc_id] })}\n\nevent: done\ndata: {"session_id":"employment-835"}\n\n`
        : 'event: error\ndata: {"code":"document_generation_failed","message":"The document could not be saved. Please retry document generation."}\n\n';
      return route.fulfill({ contentType: "text/event-stream", body: events });
    });
    const pdfBytes = contractPdf();
    await page.route("**/v1/cases/case-generated-doc/documents/doc-generated-splnomocnenie**", route => {
      expect(saved).toBe(true);
      const pdf = new URL(route.request().url()).pathname.endsWith("/pdf");
      return route.fulfill({ contentType: pdf ? "application/pdf" : "text/plain", body: pdf ? pdfBytes : contractLines.join("\n") });
    });
    await page.goto("/app/assistant");
    await page.locator(".case-item").filter({ hasText: apiCase.title }).click();
    await expect(page.locator(".assistant-thread__viewport")).toContainText("3 200 EUR");
    await expect(page.getByLabel("Generated documents")).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Stiahnuť pracovnú zmluvu" })).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath("01-unpersisted-draft.png"), fullPage: true });
    await page.getByLabel("Assistant message").fill("dobre");
    await page.getByRole("button", { name: "Send message", exact: true }).click();
    if (failFirst) {
      await expect(page.getByText("The document could not be saved.", { exact: false })).toBeVisible();
      await expect(page.getByLabel("Generated documents")).toHaveCount(0);
      await page.screenshot({ path: testInfo.outputPath("02-storage-error.png"), fullPage: true });
      await page.getByRole("button", { name: "Retry document generation", exact: true }).click();
    }
    const action = page.locator('[data-renderer="action_link"]').getByRole("link", { name: "Stiahnuť pracovnú zmluvu" });
    await expect(action).toBeVisible();
    await action.click();
    await expect(page.locator(".document-viewer-page")).toBeVisible();
    const save = page.getByRole("button", { name: /save|download/i }).first();
    await expect(save).toBeEnabled();
    const downloadEvent = page.waitForEvent("download");
    await save.click();
    const download = await downloadEvent;
    const pdfPath = testInfo.outputPath("04-generated-document.pdf");
    await download.saveAs(pdfPath);
    expect((await readFile(pdfPath)).equals(pdfBytes)).toBe(true);
    const script = "import fitz,json,sys; from pypdf import PdfReader; r=PdfReader(sys.argv[1]); d=fitz.open(sys.argv[1]); d[0].get_pixmap().save(sys.argv[2]); print(json.dumps({'pages':len(r.pages),'text':'\\n'.join(p.extract_text() for p in r.pages)}))";
    const output = execFileSync(process.env.PYTHON || "python", ["-c", script, pdfPath, testInfo.outputPath("05-pdf-first-page.png")], { encoding: "utf8" });
    const result = output.trim().split(/\r?\n/).findLast(line => line.startsWith("{"));
    expect(result, "PDF validator must emit a result").toBeTruthy();
    const parsed = JSON.parse(result!);
    expect(parsed.pages).toBe(1);
    for (const line of contractLines) expect(parsed.text).toContain(line);
    expect(attempts).toBe(failFirst ? 2 : 1);
    await writeFile(testInfo.outputPath("result-manifest.json"), JSON.stringify({
      scenario: testInfo.title, syntheticOnly: true, validation: "mocked browser regression", realE2E: "pending",
      provider: "fixture", model: "fixture", services: ["frontend"], savedDocumentId: generatedDocument.doc_id,
      pdfPages: parsed.pages, expectedTextVerified: true, attempts, retention: "Delete within 7 days after review."
    }, null, 2));
  });
}

for (const renderer of ["markdown", "structured"]) {
  test(`${renderer} PDF-only label cannot reopen the assistant without a saved document`, async ({ page, context }) => {
    const href = "/app/assistant#";
    await page.route("**/v1/cases/case-generated-doc/history?**", route => route.fulfill({ json: {
      has_more: false, documents: [], messages: [{
        communication_id: "pdf-label", role: "assistant", agent_name: "Assistant",
        content: renderer === "markdown" ? `[PDF](${href})` : "Document action",
        ...(renderer === "structured" ? { presentation: {
          ...structuredAction(href), data: { href, label: "PDF" }
        } } : {}), created_at: "2026-06-26T10:05:00Z"
      }]
    } }));
    await page.goto("/app/assistant");
    await page.locator(".case-item").filter({ hasText: apiCase.title }).click();
    await expect(page.getByRole("link", { name: "PDF", exact: true })).toHaveCount(0);
    await expect(page.getByText("The document is not ready for download.", { exact: false })).toBeVisible();
    await expect(page.getByRole("button", { name: "Retry document generation", exact: true })).toBeVisible();
    await expect(page).toHaveURL(/\/app\/assistant$/);
    expect(context.pages()).toHaveLength(1);
  });
}
