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
  await expect(page.getByRole("button", { name: /splnomocnenie_ESolutions_SK\.pdf/i })).toBeVisible();

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
