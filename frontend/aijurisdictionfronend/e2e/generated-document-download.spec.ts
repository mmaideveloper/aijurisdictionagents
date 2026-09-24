import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";

const authUser = {
  userId: "user-e2e",
  email: "marek@example.test",
  name: "Marek Matonok"
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
  await expect(page.getByText("The document has not been saved.", { exact: false })).toBeVisible();
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

for (const status of [403, 404]) {
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
