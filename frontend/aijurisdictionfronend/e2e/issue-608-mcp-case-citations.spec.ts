import { expect, test, type Page, type Route } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const authUser = {
  userId: "issue-608-synthetic-user",
  email: "issue-608@example.test",
  name: "Issue 608 Synthetic User"
};

const apiCase = {
  case_id: "issue-608-synthetic-case",
  user_id: authUser.userId,
  company_id: null,
  title: "Synthetic MCP citation case",
  status: "in_progress",
  created_at: "2026-08-08T06:00:00Z",
  updated_at: "2026-08-08T06:01:00Z"
};

const legalPrompt = "Which source governs a synthetic apartment lease in Slovakia?";
const assistantAnswer = "The retrieved source is the Slovak Civil Code, Act 40/1964 Coll.";
const citation = {
  id: "issue-608-citation",
  case_id: apiCase.case_id,
  question_message_id: "issue-608-question",
  answer_message_id: "issue-608-answer",
  source_type: "law",
  source_id: "issue-608-law-40-1964",
  source_url: "https://www.slov-lex.sk/pravne-predpisy/SK/ZZ/1964/40/",
  title: "Slovak Civil Code",
  citation_label: "40/1964 Coll. — Slovak Civil Code",
  law_number: "40/1964 Coll.",
  section: null,
  effective_from: "2026-08-08",
  court: null,
  ecli: null,
  file_number: null,
  decision_date: null,
  snippet: "Synthetic citation metadata returned by the JurisDigta MCP test fixture.",
  retrieval_tool: "JurisDigta MCP searchLaws",
  relevance_score: 1,
  created_at: "2026-08-08T06:01:00Z"
};

const fulfillJson = async (route: Route, body: unknown) => {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body)
  });
};

async function seedAuth(page: Page) {
  await page.addInitScript((user) => {
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
    window.localStorage.setItem("aj_frontend_lang", "en");
  }, authUser);
}

test("legal answer persists and displays its JurisDigta MCP case citation", async ({ page }, testInfo) => {
  let answerCompleted = false;

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
  await page.route(`**/v1/cases/${apiCase.case_id}/history?**`, (route) =>
    fulfillJson(route, {
      has_more: false,
      documents: [],
      citations: answerCompleted ? [citation] : [],
      messages: answerCompleted
        ? [
            {
              communication_id: "issue-608-question",
              role: "user",
              content: legalPrompt,
              agent_name: null,
              created_at: "2026-08-08T06:00:30Z",
              citations: []
            },
            {
              communication_id: "issue-608-answer",
              role: "assistant",
              content: assistantAnswer,
              agent_name: "LawyerSlovakia",
              created_at: "2026-08-08T06:01:00Z",
              citations: [citation]
            }
          ]
        : []
    })
  );
  await page.route("**/v1/chat/sessions", (route) =>
    fulfillJson(route, {
      id: "60860860-8608-4608-8608-608608608608",
      user_id: authUser.userId,
      case_id: apiCase.case_id,
      country: "SK",
      language: "en",
      discussion_type: "advice",
      state: "active",
      created_at: "2026-08-08T06:00:30Z"
    })
  );
  await page.route("**/v1/chat/sessions/60860860-8608-4608-8608-608608608608/stream", async (route) => {
    const request = route.request().postDataJSON() as { instruction?: string };
    expect(request.instruction).toBe(legalPrompt);
    answerCompleted = true;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: [
        "event: processing",
        'data: {"stage":"mcp_law_context","message":"JurisDigta MCP Server was contacted to retrieve the latest legal information."}',
        "",
        "event: message",
        `data: ${JSON.stringify({
          role: "assistant",
          content: assistantAnswer,
          agent_name: "LawyerSlovakia",
          citations: [citation]
        })}`,
        "",
        "event: done",
        'data: {"status":"completed"}',
        "",
        ""
      ].join("\n")
    });
  });

  await seedAuth(page);
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto("/app/assistant", { waitUntil: "domcontentloaded" });

  const caseButton = page.locator(".case-item").filter({ hasText: apiCase.title });
  await expect(caseButton).toHaveCount(1);
  await caseButton.click();
  await expect(page.getByText("No citations yet.")).toBeVisible();

  await page.getByLabel("Assistant message").fill(legalPrompt);
  await page.getByRole("button", { name: "Send message" }).click();

  await expect(page.getByText(assistantAnswer)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("40/1964 Coll. — Slovak Civil Code")).toHaveCount(2);
  await expect(page.locator(".assistant-tool-panel")).toContainText("JurisDigta MCP searchLaws");
  await expect(page.locator(".assistant-tool-panel")).not.toContainText("No citations yet.");

  const screenshotDirectory = path.resolve(process.cwd(), "../../runs/e2e/issue-608");
  const screenshotPath = path.join(screenshotDirectory, "01-mcp-case-citation-final.png");
  await mkdir(screenshotDirectory, { recursive: true });
  await page.screenshot({ path: screenshotPath, fullPage: true });
  await testInfo.attach("issue-608-mcp-case-citation-final.png", {
    path: screenshotPath,
    contentType: "image/png"
  });
});
