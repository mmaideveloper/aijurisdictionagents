import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const root = path.resolve("../..");
const output = path.join(root, "runs/e2e/issue746");
const manifestPath = path.join(output, "input-manifest.json");
const authPath = path.join(output, "private-auth.json");
test.skip(!fs.existsSync(authPath), "Prepare isolated PostgreSQL, real services and authenticate the synthetic user first.");
test.use({ viewport: { width: 1800, height: 1250 }, trace: "off", video: "off" });
test.setTimeout(240000);

test("real question produces Act 190/2003 with categories A–D and §§4–7", async ({ page, context, request }) => {
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const user = JSON.parse(fs.readFileSync(authPath, "utf8"));
  const headers = { "x-api-key": "aijuris", "x-jurisdigta-device-id": user.deviceId,
    "x-jurisdigta-device-token": user.deviceAuthToken };
  const existingResponse = await request.get(`http://127.0.0.1:8246/v1/cases?user_id=${user.userId}`, { headers });
  expect(existingResponse.ok()).toBeTruthy();
  const existing = await existingResponse.json();
  for (const previous of existing.cases ?? existing) {
    if (previous.title?.startsWith("issue746-")) {
      const removed = await request.delete(`http://127.0.0.1:8246/v1/cases/${previous.case_id}?user_id=${user.userId}`, { headers });
      expect(removed.ok()).toBeTruthy();
    }
  }
  // Real API login returned this session. No routes, answers or database responses are mocked.
  await page.addInitScript(auth => {
    sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(auth));
    localStorage.setItem("aj_frontend_lang", "sk");
  }, user);
  await page.goto("/app/case");
  await page.getByLabel("Názov prípadu", { exact: true }).fill(manifest.runId);
  await page.getByLabel("Jurisdikcia", { exact: true }).fill("Slovensko");
  await page.getByLabel("Protistrana", { exact: true }).fill("Bez protistrany – syntetický test");
  const created = page.waitForResponse(response => response.url().endsWith("/v1/cases") && response.request().method() === "POST");
  await page.locator("form button[type=submit]").click();
  const caseResponse = await created;
  expect(caseResponse.ok()).toBeTruthy();
  const caseRecord = await caseResponse.json();
  await expect(page.locator(".assistant-composer__input")).toBeVisible();
  await page.locator(".assistant-composer__input").fill(manifest.question);
  await page.locator(".assistant-composer__send").click();
  const thread = page.locator(".assistant-thread__viewport");
  await expect(thread).toContainText("190/2003", { timeout: 180000 });
  for (const section of [4, 5, 6, 7]) {
    await expect(thread).toContainText(new RegExp(`§\\s*${section}\\b`), { timeout: 180000 });
  }
  await expect(page.locator('a[href^="/sources/"]').first()).toBeVisible({ timeout: 90000 });
  const historyResponse = await request.get(`http://127.0.0.1:8246/v1/cases/${caseRecord.case_id}/history?user_id=${user.userId}`, { headers });
  expect(historyResponse.ok()).toBeTruthy();
  const history = await historyResponse.json();
  const answer = history.messages.filter((message: {role: string}) => message.role === "assistant").at(-1);
  for (const [category, section] of [["A",4],["B",5],["C",6],["D",7]]) {
    // A table names the category in its header, while each body row starts with A–D.
    // Keep the category and its expected provision on the same answer line.
    expect(answer.content).toMatch(new RegExp(`(?:(?:kategóri[aeu]|Kategóri[aeu])[^\\n]*${category}\\b|^\\s*\\|\\s*${category}\\s*\\|)[^\\n]*§\\s*${section}\\b`, "m"));
    expect(answer.citations.some((citation: {source_id: string; section: string}) =>
      citation.source_id === manifest.sourceId && new RegExp(`^§ ${section}(?:$| )`).test(citation.section))).toBeTruthy();
  }
  expect(answer.presentation.citation_bindings.length).toBeGreaterThanOrEqual(4);
  const auditResponse = await request.get(`http://127.0.0.1:8246/v1/cases/${caseRecord.case_id}/ai-model-audit?user_id=${user.userId}`, { headers });
  expect(auditResponse.ok()).toBeTruthy();
  const audit = await auditResponse.json();
  const routes = audit.entries.map((entry: { provider: string; model: string; status: string; fallback_reason: string }) => ({
    provider: entry.provider, model: entry.model, status: entry.status, fallbackReason: entry.fallback_reason,
  }));
  expect(routes.some((route: { provider: string; model: string }) =>
    route.provider.includes("azure") && route.model.includes("gpt-5-mini"))).toBeTruthy();
  expect(routes.some((route: { provider: string }) => route.provider === "mock")).toBeFalsy();
  await thread.evaluate(element => { element.scrollTop = 0; });
  await page.screenshot({ path: path.join(output, "answer-citations.png"), fullPage: true });
  const sourceLink = page.locator('a[href^="/sources/"]').first();
  await expect(sourceLink).toBeVisible();
  const newTab = context.waitForEvent("page");
  await sourceLink.click();
  const lawPage = await newTab;
  await expect(lawPage.getByTestId("full-law-text")).toContainText("§ 7", { timeout: 30000 });
  expect((await lawPage.getByTestId("full-law-text").innerText()).length).toBeGreaterThan(50000);
  await lawPage.screenshot({ path: path.join(output, "full-law.png"), fullPage: false });
  // New-case creation opens the generic workspace; reopen the saved case by its durable link.
  await page.goto(`/case/${caseRecord.case_id}`);
  await expect(thread).toContainText("190/2003", { timeout: 30000 });
  await page.reload();
  await expect(thread).toContainText("190/2003");
  for (const section of [4, 5, 6, 7]) await expect(thread).toContainText(new RegExp(`§\\s*${section}\\b`));
  fs.writeFileSync(path.join(output, "browser-result.json"), JSON.stringify({
    passed: true, runId: manifest.runId, caseId: caseRecord.case_id, question: manifest.question, routes,
    expectedSource: manifest.sourceId, expectedSections: [4,5,6,7],
    observed: answer.citations.map((citation: {source_id: string; section: string}) => ({sourceId: citation.source_id, section: citation.section})),
    reloadPassed: true, fullLawPassed: true, syntheticAccountsOnly: true,
    services: ["frontend:5189", "api:8246", "mcp:8247", "postgres:55446", "azure-foundry"],
    retention: "Delete within seven days; private authentication material is excluded from evidence."
  }, null, 2));
});
