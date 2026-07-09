import { expect, test } from "@playwright/test";

const authUser = {
  userId: "user-case-link-e2e",
  email: "case-link@example.test",
  name: "Case Link User"
};

const apiCase = {
  case_id: "case-email-link",
  user_id: authUser.userId,
  company_id: null,
  title: "Email linked case",
  status: "in_progress",
  created_at: "2026-07-09T10:00:00Z",
  updated_at: "2026-07-09T10:10:00Z"
};

const generatedDocument = {
  doc_id: "doc-email-link-pdf",
  kind: "generated_document",
  version: 1,
  original_filename: "splnomocnenie-email-link.pdf",
  processing_status: "processed",
  processing_error: null,
  processed_at: "2026-07-09T10:10:00Z",
  created_at: "2026-07-09T10:10:00Z"
};

test.beforeEach(async ({ page }) => {
  await page.route("**/v1/model-routing/effective?**", async (route) => {
    await route.fulfill({
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
    });
  });

  await page.route("**/v1/cases?user_id=**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([apiCase])
    });
  });

  await page.route("**/v1/cases/case-email-link/history?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        has_more: false,
        documents: [generatedDocument],
        citations: [],
        messages: [
          {
            communication_id: "msg-client",
            role: "user",
            content: "Prosim priprav splnomocnenie.",
            agent_name: null,
            created_at: "2026-07-09T10:00:00Z",
            citations: []
          },
          {
            communication_id: "msg-lawyer",
            role: "assistant",
            content:
              "Splnomocnenie je pripravene na kontrolu.\n\n" +
              "Generated document:\n" +
              "- [splnomocnenie-email-link.pdf](/app/documents/view?caseId=case-email-link&docId=doc-email-link-pdf&kind=generated_document&filename=splnomocnenie-email-link.pdf&caseTitle=Email+linked+case&userId=user-case-link-e2e)",
            agent_name: "AI Lawyer",
            created_at: "2026-07-09T10:10:00Z",
            citations: []
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

test("authenticated case deep link opens latest communication and generated documents", async ({
  page
}) => {
  await page.goto("/case/case-email-link", { waitUntil: "domcontentloaded" });

  await expect(page.getByRole("heading", { name: "JurisDigta Assistant" })).toBeVisible();
  await expect(page.getByText("Local Ollama - qwen3:1.7b")).toBeVisible();
  await expect(page.locator(".assistant-thread__viewport")).toContainText(
    "Splnomocnenie je pripravene na kontrolu."
  );
  await expect(
    page.getByRole("link", { name: /splnomocnenie-email-link\.pdf/i })
  ).toBeVisible();

  await page.screenshot({
    path: "../../runs/e2e/case-deep-link.png",
    fullPage: true
  });
});
