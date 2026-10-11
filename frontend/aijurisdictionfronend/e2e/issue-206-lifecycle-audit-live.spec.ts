import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { existsSync } from "node:fs";
import { readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
const fixture = path.resolve("../../runs/e2e/issue864");
const authPath = path.join(fixture, "private-auth.json");
const inputPath = path.join(fixture, "input-manifest.json");
const api = "http://127.0.0.1:8264";
test.skip(!existsSync(authPath) || !existsSync(inputPath), "Prepare and authenticate the real #206 fixture.");
test.use({ trace: "off", video: "off" });
test.setTimeout(600_000);
test("parallel real browser requests stay isolated and disconnected receipt is not fabricated", async ({ browser, request }) => {
  const input = JSON.parse(await readFile(inputPath, "utf8"));
  const auth = JSON.parse(await readFile(authPath, "utf8"));
  expect(input.syntheticOnly).toBe(true);
  const userHeaders = { "x-api-key": "aijuris", "x-jurisdigta-device-id": auth.workflowUser.deviceId, "x-jurisdigta-device-token": auth.workflowUser.deviceAuthToken };
  const adminHeaders = { "x-api-key": "aijuris", "x-jurisdigta-device-id": auth.adminUser.deviceId, "x-jurisdigta-device-token": auth.adminUser.deviceAuthToken, "x-jurisdigta-admin-user-id": auth.adminUser.userId };
  const contexts: BrowserContext[] = [];
  const cases: string[] = [];
  const question = "Ako sa číta označenie § 569 ods. 1 zákona 40/1964 Z. z. v právnej citácii? Vysvetli význam paragrafu, odseku a čísla zákona s citáciou dostupného zdroja.";
  try {
    const pages: Page[] = [];
    for (const index of [0, 1]) {
      const context = await browser.newContext({ viewport: { width: 1800, height: 1200 } });
      contexts.push(context);
      await context.addInitScript(user => { sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user)); localStorage.setItem("aj_frontend_lang", "sk"); }, auth.workflowUser);
      const page = await context.newPage(); pages.push(page);
      if (index === 0) {
      await page.goto("http://127.0.0.1:5189/app/case");
      await page.getByLabel("Názov prípadu", { exact: true }).fill(`${input.caseTitle} parallel-${index}`);
      await page.getByLabel("Protistrana", { exact: true }).fill("Syntetická protistrana");
      const [created] = await Promise.all([page.waitForResponse(r => r.url().endsWith("/v1/cases") && r.request().method() === "POST"), page.locator("form button[type=submit]").click()]);
      expect(created.ok()).toBe(true); cases.push((await created.json()).case_id);
      await page.waitForURL("**/app/assistant");
      }
      await page.goto(`http://127.0.0.1:5189/case/${cases[0]}`);
      await page.waitForLoadState("networkidle");
      await expect(page.getByLabel("AI model použitý pre tento chat")).toContainText(input.expectedModel);
    }
    async function send(page: Page) {
      await page.locator(".assistant-composer__input").fill(question);
      const [response] = await Promise.all([page.waitForResponse(r => r.url().endsWith("/stream") && r.request().method() === "POST", { timeout: 60_000 }), page.locator(".assistant-composer__send").click()]);
      expect(response.ok()).toBe(true); return response;
    }
    const streams = await Promise.all(pages.map(send));
    await Promise.all(streams.map(async response => expect(await response.text()).toContain('"status": "generic"')));
    const ids = streams.map(response => ({ request: response.request().headers()["x-request-id"]!, correlation: response.request().headers()["x-correlation-id"]! }));
    expect(ids[0]!.request).not.toBe(ids[1]!.request);
    expect(ids[0]!.correlation).not.toBe(ids[1]!.correlation);
    for (const [index, identity] of ids.entries()) {
      const response = await request.get(`${api}/v1/admin/debug/${identity.correlation}`, { headers: adminHeaders });
      expect(response.ok()).toBe(true); const trace = await response.json();
      expect(trace.timeline.some((event: { request_id: string }) => event.request_id === ids[1-index]!.request)).toBe(false);
      expect(trace.timeline.some((event: { component: string; status: string; payload: { model?: string; provider?: string } }) => event.component === "model" && event.status === "completed" && event.payload.model === input.expectedModel && event.payload.provider?.includes("azure"))).toBe(true);
      const history = await request.get(`${api}/v1/cases/${cases[0]}/history`, { headers: userHeaders, params: { user_id: auth.workflowUser.userId } });
      expect(history.ok()).toBe(true);
      expect((await history.json()).citations.some((item: { source_id: string }) => item.source_id === input.expectedLegalSourceId)).toBe(true);
    }
    const page = pages[0]!;
    await page.goto(`http://127.0.0.1:5189/case/${cases[0]}`);
    await page.waitForLoadState("networkidle");
    await expect(page.getByText(question, { exact: true }).first()).toBeVisible();
    const interrupted = await send(page);
    const interruptedRequest = interrupted.request().headers()["x-request-id"]!;
    const interruptedCorrelation = interrupted.request().headers()["x-correlation-id"]!;
    await expect.poll(async () => {
      const response = await request.get(`${api}/v1/admin/debug/${interruptedCorrelation}`, { headers: adminHeaders });
      if (!response.ok()) return false;
      return (await response.json()).timeline.some((event: { component: string; stage: string; parent_request_id: string }) => event.component === "frontend" && event.stage === "headers_received" && event.parent_request_id === interruptedRequest);
    }, { timeout: 30_000 }).toBe(true);
    await page.screenshot({ path: path.join(input.evidenceRoot, "issue-206-before-browser-disconnect.png"), fullPage: true });
    await contexts[0]!.close();
    contexts.shift();
    await expect.poll(async () => {
      const response = await request.get(`${api}/v1/admin/debug/${interruptedCorrelation}`, { headers: adminHeaders });
      if (!response.ok()) return false;
      return (await response.json()).timeline.some((event: { stage: string; status: string; parent_request_id: string }) => event.stage === "chat_session_worker" && ["completed", "failed"].includes(event.status) && event.parent_request_id === interruptedRequest);
    }, { timeout: 180_000 }).toBe(true);
    const after = await request.get(`${api}/v1/admin/debug/${interruptedCorrelation}`, { headers: adminHeaders });
    expect(after.ok()).toBe(true); const interruptedTrace = await after.json();
    expect(interruptedTrace.timeline.some((event: { component: string; stage: string; parent_request_id: string }) => event.component === "frontend" && event.stage === "stream_completed" && event.parent_request_id === interruptedRequest)).toBe(false);
    const restored = pages[1]!;
    await restored.goto(`http://127.0.0.1:5189/case/${cases[0]}`);
    await restored.waitForLoadState("networkidle");
    await expect(restored.getByText(question, { exact: true }).first()).toBeVisible();
    await restored.screenshot({ path: path.join(input.evidenceRoot, "issue-206-reloaded-history.png"), fullPage: true });
    await writeFile(path.join(input.evidenceRoot, "lifecycle-result-manifest.json"), JSON.stringify({ passed: true, syntheticOnly: true, runId: input.runId, parallelRequests: ids, interruptedRequest, interruptedCorrelation, completedReceiptRecorded: false, preservedCaseHistory: true, provider: "azurefoundry", model: input.expectedModel, expectedSourceIds: [input.expectedLegalSourceId], observedSourceIds: [input.expectedLegalSourceId], services: ["frontend:5189", "api:8264", "mcp:8364", "loopback-postgresql"], fault: "real browser context closed after response headers; no intercepted responses", retention: "Seven days maximum" }, null, 2));
  } finally {
    for (const context of contexts) { await context.setOffline(false); await context.close(); }
    for (const caseId of cases) expect((await request.delete(`${api}/v1/cases/${caseId}`, { headers: userHeaders, params: { user_id: auth.workflowUser.userId } })).ok()).toBe(true);
    await rm(authPath, { force: true });
  }
});
