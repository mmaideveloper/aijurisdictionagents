import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test, type Route } from "@playwright/test";

const authUser = {
  userId: "issue-529-user",
  email: "issue-529@example.test",
  name: "Issue 529 Reviewer"
};

const apiCase = {
  case_id: "issue-529-case",
  user_id: authUser.userId,
  company_id: null,
  title: "issue 529 mcp proof",
  status: "in_progress",
  created_at: "2026-07-14T08:00:00Z",
  updated_at: "2026-07-14T08:00:00Z"
};

const proofNotice = "JurisDigta MCP server bol kontaktovaný na získanie najnovších právnych informácií.";
const summaryAnswer = "Súhrn zákona 192/2026 bol pripravený z kontextu získaného cez JurisDigta MCP server.";
const screenshotPath = resolve(process.cwd(), "../../runs/e2e/issue-529-mcp-proof-message.png");

const fulfillJson = async (route: Route, body: unknown) => {
  await route.fulfill({
    contentType: "application/json",
    body: JSON.stringify(body)
  });
};

const emptyHistory = {
  has_more: false,
  documents: [],
  citations: [],
  messages: []
};

test("shows user-visible proof when law summary uses JurisDigta MCP", async ({ page }) => {
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
  await page.route("**/v1/model-routing/selectable?**", (route) =>
    fulfillJson(route, { eligible: false, profiles: [] })
  );
  await page.route("**/v1/cases?user_id=**", (route) => fulfillJson(route, [apiCase]));
  await page.route("**/v1/cases/issue-529-case/history?**", (route) => fulfillJson(route, emptyHistory));
  await page.route("**/v1/chat/sessions", (route) =>
    fulfillJson(route, {
      id: "issue-529-session",
      user_id: authUser.userId,
      case_id: apiCase.case_id,
      country: "SK",
      language: "sk",
      discussion_type: "advice",
      state: "active",
      created_at: "2026-07-14T08:01:00Z"
    })
  );
  await page.route("**/v1/chat/sessions/issue-529-session/stream", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: [
        "event: processing",
        `data: ${JSON.stringify({
          stage: "mcp_law_context",
          message: proofNotice,
          details: {
            source: "jurisdigta_mcp_server",
            tool: "searchLaws",
            law_number: "192/2026",
            user_visible: true,
            web_search_status: "not_requested",
            source_notice_i18n: {
              sk: proofNotice,
              de: "Der JurisDigta MCP-Server wurde kontaktiert, um aktuelle Rechtsinformationen abzurufen.",
              en: "JurisDigta MCP Server was contacted to retrieve the latest legal information."
            }
          }
        })}`,
        "",
        "event: message",
        `data: ${JSON.stringify({
          id: "issue-529-message",
          session_id: "issue-529-session",
          role: "assistant",
          content: summaryAnswer,
          agent_name: "LawyerSlovakia",
          created_at: "2026-07-14T08:01:01Z"
        })}`,
        "",
        "event: done",
        'data: {"session_id":"issue-529-session","status":"completed"}',
        "",
        ""
      ].join("\n")
    });
  });

  await page.addInitScript((user) => {
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
    window.localStorage.setItem("aj_frontend_lang", "sk");
  }, authUser);

  await page.goto("/app/assistant", { waitUntil: "domcontentloaded" });

  const caseButton = page.locator(".case-item").filter({ hasText: apiCase.title }).first();
  await expect(caseButton).toBeVisible();
  await caseButton.click();

  await page.locator(".assistant-composer__input").fill("Daj mi sumar zo zakona 192/2026");
  await page.getByRole("button", { name: "Odoslať správu" }).click();

  const thread = page.locator(".assistant-thread__viewport");
  await expect(thread).toContainText(proofNotice);
  await expect(thread).toContainText(summaryAnswer);

  mkdirSync(resolve(process.cwd(), "../../runs/e2e"), { recursive: true });
  await page.screenshot({
    path: screenshotPath,
    fullPage: true,
    animations: "disabled"
  });
});
