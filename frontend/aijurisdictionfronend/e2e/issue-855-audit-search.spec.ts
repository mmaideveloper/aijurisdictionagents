import { expect, test } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

// Preliminary browser regression only. Intercepted data is not real-local acceptance.
test("synthetic admin searches trace metadata and selects protected diagnostics", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1600, height: 1200 });
  const runId = `issue-855-browser-${Date.now()}`;
  const evidence = path.resolve("../../runs/e2e/issue-855", runId);
  await mkdir(evidence, { recursive: true });
  await page.addInitScript(() => {
    sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify({
      userId: "synthetic-admin-855", email: "synthetic-admin@example.test", name: "Synthetic Audit Admin",
      role: "admin", isEnabled: true
    }));
    localStorage.setItem("aj_frontend_lang", "en");
  });
  await page.route("**/v1/admin/ai-models", (route) => route.fulfill({ json: {
    providers: [], profiles: [], credentials: [], policies: [], groups: [], memberships: [], users: [],
    users_page: { total: 0, limit: 25, offset: 0 }, audit_events: [], route_priority: [], compliance_notes: [], grafana_url: ""
  } }));
  await page.route("**/v1/admin/ai-models/ollama/models", (route) => route.fulfill({ json: { models: [] } }));
  const createdAt = new Date().toISOString();
  const item = { correlation_id: "synthetic-correlation-855", session_id: "synthetic-session-855",
    user_id: "synthetic-user-855", case_id: "synthetic-case-855", created_at: createdAt,
    expires_at: new Date(Date.now() + 7 * 86400000).toISOString() };
  let observedFilters: Record<string, string> = {};
  await page.route("**/v1/admin/debug?**", (route) => {
    observedFilters = Object.fromEntries(new URL(route.request().url()).searchParams);
    return route.fulfill({ json: { items: [item], next_cursor: null, start: createdAt, end: createdAt, limit: 25, retention_days: 7 } });
  });
  await page.route("**/v1/admin/debug/synthetic-correlation-855", (route) => route.fulfill({ json: {
    correlation_id: item.correlation_id, retention_days: 7, generated_at: createdAt, session: null, messages: [],
    timeline: [{ kind: "decision", event_id: "synthetic-event-855", created_at: createdAt,
      correlation_id: item.correlation_id, session_id: item.session_id, component: "langgraph",
      stage: "synthetic_review", status: "completed", payload: { reason_code: "synthetic_review_complete" } }],
    flow: { nodes: [], edges: [] }, warnings: [],
    langgraph_evidence: { schema_version: 1, runs: [], completeness: "complete", page: { limit: 25, offset: 0, returned_events: 0, has_more: false, next_offset: null } }
  } }));
  await page.goto("/app/admin");
  await page.getByRole("button", { name: "Debug", exact: true }).click();
  await page.getByLabel("User ID", { exact: true }).fill(item.user_id);
  await page.getByLabel("Case ID", { exact: true }).fill(item.case_id);
  await page.getByRole("button", { name: "Search logs" }).click();
  await expect(page.getByRole("status")).toHaveText("Matching traces");
  expect(observedFilters.user_id).toBe(item.user_id);
  expect(observedFilters.case_id).toBe(item.case_id);
  await page.getByRole("button", { name: item.correlation_id, exact: true }).click();
  await expect(page.getByText("langgraph → synthetic_review", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Export for Codex" })).toBeVisible();
  const screenshot = path.join(evidence, "issue-855-search-selected-trace.png");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: screenshot, fullPage: true });
  await testInfo.attach("Synthetic browser regression — not real-model E2E", { path: screenshot, contentType: "image/png" });
  await writeFile(path.join(evidence, "result-manifest.json"), JSON.stringify({
    runId, syntheticOnly: true, acceptance: "preliminary-browser-regression", backend: "intercepted",
    realLocalE2E: "pending: Docker/PostgreSQL unavailable", expectedFilters: { user_id: item.user_id, case_id: item.case_id },
    observedFilters, screenshot: path.basename(screenshot), retention: "Delete within seven days."
  }, null, 2));
});
