import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const authUser = {
  userId: "user-delete-controls-e2e",
  email: "delete-controls@example.test",
  name: "Delete Controls Test User"
};

const apiCase = {
  case_id: "case-delete-controls",
  user_id: authUser.userId,
  company_id: null,
  title: "Loan agreement deletion test",
  status: "in_progress",
  created_at: "2026-08-05T12:00:00Z",
  updated_at: "2026-08-05T12:05:00Z"
};

const uploadedDocument = {
  doc_id: "doc-uploaded-delete",
  kind: "uploaded",
  version: 1,
  original_filename: "client-evidence.pdf",
  processing_status: "processed",
  processing_error: null,
  processed_at: "2026-08-05T12:02:00Z",
  created_at: "2026-08-05T12:01:00Z"
};

const generatedDocument = {
  doc_id: "doc-generated-delete",
  kind: "generated_document",
  version: 1,
  original_filename: "loan-agreement.pdf",
  processing_status: "processed",
  processing_error: null,
  processed_at: "2026-08-05T12:04:00Z",
  created_at: "2026-08-05T12:03:00Z"
};

test("deletes documents with a visible audit event and soft-deletes the active case", async ({
  page
}, testInfo) => {
  let caseDeleted = false;
  let documents = [uploadedDocument, generatedDocument];
  const messages = [
    {
      communication_id: "message-initial",
      role: "assistant",
      content: "The case documents are ready for review.",
      agent_name: "AI Lawyer",
      created_at: "2026-08-05T12:05:00Z",
      citations: []
    }
  ];

  await page.route("**/v1/model-routing/effective?**", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        plan_code: "free",
        route_type: "free_local",
        provider: "local_ollama",
        provider_display_name: "Local Ollama",
        model: "qwen3:1.7b",
        model_profile_id: "local_ollama_default",
        is_local: true,
        is_external: false,
        label: "Local Ollama - qwen3:1.7b"
      })
    })
  );
  await page.route("**/v1/cases?user_id=**", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(caseDeleted ? [] : [apiCase])
    })
  );
  await page.route("**/v1/cases/case-delete-controls/history?**", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ has_more: false, citations: [], documents, messages })
    })
  );
  await page.route("**/v1/cases/case-delete-controls/documents/*?**", async (route) => {
    if (route.request().method() !== "DELETE") {
      await route.fallback();
      return;
    }
    const docId = route.request().url().includes("doc-uploaded-delete")
      ? "doc-uploaded-delete"
      : "doc-generated-delete";
    documents = documents.filter((document) => document.doc_id !== docId);
    messages.push({
      communication_id: "message-document-deleted",
      role: "system",
      content: "Document deleted at 2026-08-05T13:00:00Z.",
      agent_name: "System",
      created_at: "2026-08-05T13:00:00Z",
      citations: []
    });
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        event_id: "event-document-deleted",
        case_id: apiCase.case_id,
        doc_id: docId,
        document_kind: "uploaded",
        outcome: "deleted",
        deleted_at: "2026-08-05T13:00:00Z",
        communication_id: "message-document-deleted",
        correlation_id: "correlation-delete-e2e"
      })
    });
  });
  await page.route("**/v1/cases/case-delete-controls?user_id=**", async (route) => {
    expect(route.request().method()).toBe("DELETE");
    caseDeleted = true;
    await route.fulfill({ status: 204, body: "" });
  });
  await page.addInitScript((user) => {
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
    window.localStorage.setItem("aj_frontend_lang", "en");
  }, authUser);

  await page.goto("/app/assistant", { waitUntil: "domcontentloaded" });
  const caseCard = page.locator(".case-item-container").filter({ hasText: apiCase.title });
  await caseCard.locator(".case-item").click();
  await expect(caseCard.getByRole("button", { name: "Export case" })).toBeVisible();
  await expect(caseCard.getByRole("button", { name: "Delete case" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete document client-evidence.pdf" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete document loan-agreement.pdf" })).toBeVisible();

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete document client-evidence.pdf" }).click();
  await expect(page.getByText("client-evidence.pdf")).toHaveCount(0);
  await expect(page.getByText("Document deleted at 2026-08-05T13:00:00Z.")).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Document deleted");

  const screenshotDirectory = path.resolve("..", "..", "output", "playwright");
  await mkdir(screenshotDirectory, { recursive: true });
  const screenshotPath = path.join(screenshotDirectory, "issue-597-delete-controls.png");
  await page.screenshot({ path: screenshotPath, fullPage: true });
  await testInfo.attach("issue-597-delete-controls", {
    path: screenshotPath,
    contentType: "image/png"
  });

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete case" }).click();
  await expect(page.getByText(apiCase.title)).toHaveCount(0);
  await expect(page.getByText("No cases found in the database yet.")).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("Case deleted.");
});
