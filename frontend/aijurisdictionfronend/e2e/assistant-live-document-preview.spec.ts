import { expect, test, type Page, type Route } from "@playwright/test";

const authUser = {
  userId: "issue-503-user",
  email: "issue-503@example.test",
  name: "Issue 503 Test User"
};

const apiCase = {
  case_id: "issue-503-case",
  user_id: authUser.userId,
  company_id: null,
  title: "issue 503 live preview",
  status: "in_progress",
  created_at: "2026-07-09T08:00:00Z",
  updated_at: "2026-07-09T08:05:00Z"
};

const generatedDocument = {
  doc_id: "issue-503-splnomocnenie",
  kind: "generated_document",
  version: 1,
  original_filename: "splnomocnenie_issue_503.pdf",
  processing_status: "processed",
  processing_error: null,
  processed_at: "2026-07-09T08:05:00Z",
  created_at: "2026-07-09T08:05:00Z"
};

const draftDocument = `Splnomocnenie je pripravene na kontrolu.

**Splnomocnenie**

Ja, dolu podpisany Marek Matonok, tymto splnomocnujem Emiliu Testovu na pouzivanie firemneho motoroveho vozidla ESolutions SK s.r.o.

SPZ vozidla: PP472DT

Datum: 9. jula 2026
Podpis: ______________________`;

const hydratedAssistantContent = `${draftDocument}

Generated document:
- [splnomocnenie_issue_503.pdf](/app/documents/view?caseId=issue-503-case&docId=issue-503-splnomocnenie&kind=generated_document&filename=splnomocnenie_issue_503.pdf&caseTitle=issue+503+live+preview&userId=issue-503-user)`;

const citation = {
  id: "issue-503-citation",
  case_id: apiCase.case_id,
  question_message_id: "issue-503-user-message",
  answer_message_id: "issue-503-assistant-message",
  source_type: "law",
  source_id: "slov-lex-obciansky-zakonnik",
  source_url: "https://www.slov-lex.sk/",
  title: "Obciansky zakonnik",
  citation_label: "Obciansky zakonnik",
  law_number: "40/1964 Zb.",
  section: null,
  effective_from: "2026-07-09",
  court: null,
  ecli: null,
  file_number: null,
  decision_date: null,
  snippet: "Plnomocenstvo vyzaduje identifikaciu splnomocnitela, splnomocnenca a rozsah opravnenia.",
  retrieval_tool: "JurisDigta MCP searchLaws",
  relevance_score: 1,
  created_at: "2026-07-09T08:05:00Z"
};

const historyBeforeGeneration = {
  has_more: false,
  documents: [],
  citations: [],
  messages: [
    {
      communication_id: "issue-503-existing-user",
      role: "user",
      content: "Priprav splnomocnenie.",
      agent_name: null,
      created_at: "2026-07-09T08:01:00Z"
    }
  ]
};

const historyAfterGeneration = {
  has_more: false,
  documents: [generatedDocument],
  citations: [citation],
  messages: [
    {
      communication_id: "issue-503-user-message",
      role: "user",
      content: "Priprav splnomocnenie pre Emiliu Testovu na firemne auto PP472DT.",
      agent_name: null,
      created_at: "2026-07-09T08:04:00Z"
    },
    {
      communication_id: "issue-503-assistant-message",
      role: "assistant",
      content: hydratedAssistantContent,
      agent_name: "LawyerSlovakia",
      created_at: "2026-07-09T08:05:00Z",
      citations: [citation]
    }
  ]
};

const fulfillJson = async (route: Route, body: unknown) => {
  await route.fulfill({
    contentType: "application/json",
    body: JSON.stringify(body)
  });
};

const fulfillStream = async (route: Route) => {
  await route.fulfill({
    status: 200,
    contentType: "text/event-stream",
    body: [
      "event: processing",
      'data: {"stage":"drafting","message":"Teraz vytvorim PDF dokument. Chvilu prosim."}',
      "",
      "event: message",
      `data: ${JSON.stringify({
        id: "issue-503-stream-message",
        session_id: "issue-503-session",
        role: "assistant",
        content: "Teraz vytvorim PDF dokument. Chvilu prosim.",
        agent_name: "LawyerSlovakia",
        created_at: "2026-07-09T08:04:30Z"
      })}`,
      "",
      "event: done",
      'data: {"session_id":"issue-503-session","status":"completed"}',
      "",
      ""
    ].join("\n")
  });
};

async function seedAuth(page: Page) {
  await page.addInitScript((user) => {
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
    window.localStorage.setItem("aj_frontend_lang", "en");
  }, authUser);
}

test("assistant live response keeps formatted document preview, generated PDF action, and citations after reload", async ({
  page,
  context
}, testInfo) => {
  let generationFinished = false;
  let pdfRouteHit = false;

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
      label: "Local Ollama - qwen3:1.7b"
    })
  );
  await page.route("**/v1/cases?user_id=**", (route) => fulfillJson(route, [apiCase]));
  await page.route("**/v1/cases/issue-503-case/history?**", (route) =>
    fulfillJson(route, generationFinished ? historyAfterGeneration : historyBeforeGeneration)
  );
  await page.route("**/v1/chat/sessions", (route) =>
    fulfillJson(route, {
      id: "issue-503-session",
      user_id: authUser.userId,
      case_id: apiCase.case_id,
      country: "SK",
      language: "en",
      discussion_type: "advice",
      state: "active",
      created_at: "2026-07-09T08:04:00Z"
    })
  );
  await page.route("**/v1/chat/sessions/issue-503-session/stream", async (route) => {
    generationFinished = true;
    await fulfillStream(route);
  });
  await context.route("**/v1/cases/issue-503-case/documents/issue-503-splnomocnenie/pdf?**", async (route) => {
    pdfRouteHit = true;
    await route.fulfill({
      status: 200,
      contentType: "application/pdf",
      headers: {
        "Content-Disposition": 'inline; filename="splnomocnenie_issue_503.pdf"'
      },
      body: "%PDF-1.4\n% issue 503 generated document\n%%EOF"
    });
  });

  await seedAuth(page);
  await page.goto("/app/assistant", { waitUntil: "domcontentloaded" });

  const caseButton = page.locator(".case-item").filter({ hasText: apiCase.title }).first();
  await expect(caseButton).toBeVisible();
  await caseButton.click();

  await page.getByLabel("Assistant message").fill("Priprav splnomocnenie pre Emiliu Testovu na firemne auto PP472DT.");
  await page.getByRole("button", { name: "Send message" }).click();

  const preview = page.locator(".assistant-document-preview").first();
  await expect(preview).toBeVisible({ timeout: 15_000 });
  await expect(preview.getByRole("heading", { name: "Splnomocnenie" })).toBeVisible();
  await expect(preview).toContainText("Emiliu Testovu");
  await expect(preview).toContainText("PP472DT");
  await expect(page.locator(".assistant-thread__viewport")).not.toContainText("Teraz vytvorim PDF dokument");
  await expect(page.locator(".assistant-thread__viewport")).not.toContainText("**");

  const generatedAction = page.getByLabel("Generated documents").getByRole("link", {
    name: /splnomocnenie_issue_503\.pdf/
  });
  await expect(generatedAction).toBeVisible();
  await expect(page.locator(".case-item").filter({ hasText: /1 legal document/ }).first()).toBeVisible();
  await expect(page.getByText("Obciansky zakonnik").first()).toBeVisible();
  await expect(page.getByText("JurisDigta MCP searchLaws").first()).toBeVisible();

  await testInfo.attach("issue-503-live-preview.png", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png"
  });

  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator(".case-item").filter({ hasText: apiCase.title }).first()).toBeVisible();
  await page.locator(".case-item").filter({ hasText: apiCase.title }).first().click();
  await expect(page.locator(".assistant-document-preview").first()).toBeVisible();
  await expect(
    page.getByLabel("Generated documents").getByRole("link", { name: /splnomocnenie_issue_503\.pdf/ })
  ).toBeVisible();

  const viewerPromise = context.waitForEvent("page");
  await page.getByLabel("Generated documents").getByRole("link", { name: /splnomocnenie_issue_503\.pdf/ }).click();
  const viewer = await viewerPromise;
  await viewer.waitForLoadState("domcontentloaded");
  await expect(viewer).toHaveURL(/\/app\/documents\/view/);
  await expect(viewer.getByText("splnomocnenie_issue_503.pdf")).toBeVisible();
  await expect.poll(() => pdfRouteHit).toBe(true);
  await viewer.close();
});
