import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const directory = path.resolve("../../runs/issue661");
const manifestPath = path.join(directory, "input-manifest.json");
const authPath = path.join(directory, "private-auth.json");
const api = "http://127.0.0.1:8661";
test.skip(!existsSync(manifestPath) || !existsSync(authPath), "Start scripts/run_issue_661_e2e_services.py and authenticate the synthetic user first.");
test.use({ viewport: { width: 1800, height: 1200 }, trace: "off", video: "off" });
test.setTimeout(180_000);

test("real frontend native tools preserve the PostgreSQL source and model route", async ({ page, request }) => {
  const input = JSON.parse(await readFile(manifestPath, "utf8"));
  const auth = JSON.parse(await readFile(authPath, "utf8"));
  expect(input.syntheticOnly).toBe(true);
  const headers = { "x-api-key": "aijuris", "x-jurisdigta-device-id": auth.deviceId,
    "x-jurisdigta-device-token": auth.deviceAuthToken };
  const previous = await request.get(`${api}/v1/cases`, { headers, params: { user_id: auth.userId } });
  expect(previous.ok()).toBe(true);
  for (const row of await previous.json()) {
    if (row.title.startsWith("[issue661-")) {
      const removed = await request.delete(`${api}/v1/cases/${row.case_id}`, {
        headers, params: { user_id: auth.userId } });
      expect(removed.ok()).toBe(true);
    }
  }
  await page.addInitScript(user => {
    sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
    localStorage.setItem("aj_frontend_lang", "sk");
  }, auth);
  await page.goto("http://127.0.0.1:8663/app/case");
  await page.getByLabel("Názov prípadu", { exact: true }).fill(`[${input.runId}] Syntetický test nástrojov`);
  await page.getByLabel("Protistrana", { exact: true }).fill("Bez protistrany – syntetický test");
  const creation = page.waitForResponse(r => r.url().endsWith("/v1/cases") && r.request().method() === "POST");
  await page.locator("form button[type=submit]").click();
  const created = await creation;
  expect(created.ok()).toBe(true);
  const caseId = (await created.json()).case_id;
  const listed = await request.get(`${api}/v1/cases`, { headers, params: { user_id: auth.userId } });
  expect(listed.ok()).toBe(true);
  expect((await listed.json()).some((row: { case_id: string }) => row.case_id === caseId)).toBe(true);
  await page.goto(`http://127.0.0.1:8663/case/${caseId}`);
  await page.waitForLoadState("networkidle");
  const composer = page.locator(".assistant-composer__input");
  await expect(composer).toBeEnabled({ timeout: 30_000 });
  await composer.fill("Over presný text § 1 syntetického zákona 661/2026. Pri vyhľadaní použi len označenie 661/2026 a pri získaní textu presný identifikátor vrátený nástrojom. Vysvetli výsledok a cituj zdroj. Ide výhradne o syntetický test, nie o skutočný zákon.");
  const pending = page.waitForResponse(r => r.url().endsWith("/stream") && r.request().method() === "POST");
  await page.locator(".assistant-composer__send").click();
  const stream = await pending;
  expect(stream.ok()).toBe(true);
  const events = await stream.text();
  const loop = events.split("\n").filter(line => line.startsWith("data: "))
    .map(line => JSON.parse(line.slice(6))).find(event => event.stage === "agent_tool_loop");
  expect(loop?.details.terminal_reason).toBe("completed");
  const count = Number(loop?.details.tool_call_count ?? 0);
  expect(count).toBeGreaterThan(0);
  const toolIds = loop.details.tool_ids;
  expect(toolIds).toContain("getLawText");
  expect(loop.details.citations.map((row: { source_id: string }) => row.source_id)).toContain(input.sourceId);
  const historyResponse = await request.get(`${api}/v1/cases/${caseId}/history`, {
    headers, params: { user_id: auth.userId } });
  expect(historyResponse.ok()).toBe(true);
  const history = await historyResponse.json();
  const answer = history.messages.filter((row: { role: string }) => row.role === "assistant").at(-1);
  const observed = (answer?.citations ?? []).map((row: { source_id: string }) => row.source_id);
  expect(observed).toContain(input.sourceId);
  await expect(page.locator(".assistant-message").last()).toBeVisible();
  await expect(page.locator(".assistant-message").last()).toContainText("právny asistent overí zdroj");
  await expect(page.getByText("661/2026", { exact: false }).last()).toBeVisible();
  const auditResponse = await request.get(`${api}/v1/cases/${caseId}/ai-model-audit`, {
    headers, params: { user_id: auth.userId } });
  expect(auditResponse.ok()).toBe(true);
  const routes = (await auditResponse.json()).entries.filter((row: { audit_metadata?: { model_used?: boolean } }) => row.audit_metadata?.model_used);
  expect(routes.some((row: { provider: string; model: string }) => row.provider === input.expectedProvider && row.model === input.expectedModel)).toBe(true);
  await page.screenshot({ path: path.join(directory, "final-state.png"), fullPage: true });
  await writeFile(path.join(directory, "result.json"), JSON.stringify({
    passed: true, runId: input.runId, syntheticOnly: true, caseId,
    expectedSourceId: input.sourceId, observedSourceIds: observed,
    provider: input.expectedProvider, model: input.expectedModel,
    terminalReason: "completed", toolCalls: count, toolIds, services: input.services,
    screenshot: "final-state.png", retentionDays: 7,
  }, null, 2));
});
