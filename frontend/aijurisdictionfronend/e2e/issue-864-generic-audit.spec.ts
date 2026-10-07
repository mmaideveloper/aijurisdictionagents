import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";

const directory = path.resolve("../../runs/e2e/issue864");
const manifestPath = path.join(directory, "input-manifest.json");
const authPath = path.join(directory, "private-auth.json");
const api = "http://127.0.0.1:8264";
test.skip(!existsSync(manifestPath) || !existsSync(authPath), "Prepare issue #864 real PostgreSQL/services and real synthetic login first.");
test.use({ viewport: { width: 1800, height: 1200 }, trace: "off", video: "off" });
test.setTimeout(600_000);

test("generic chat appears in the full audit with actual LangGraph and model/MCP logs", async ({ page, request }) => {
  const input = JSON.parse(await readFile(manifestPath, "utf8"));
  const auth = JSON.parse(await readFile(authPath, "utf8"));
  expect(input.syntheticOnly).toBe(true);
  expect(input.expectedProvider.toLowerCase()).toContain("azure");
  const headers = (user: typeof auth.workflowUser) => ({
    "x-api-key": "aijuris", "x-jurisdigta-device-id": user.deviceId,
    "x-jurisdigta-device-token": user.deviceAuthToken,
  });
  await mkdir(input.evidenceRoot, { recursive: true });
  let caseId = "";
  try {
    // These sessions were issued by the real sign-in endpoint, never fabricated.
    await page.addInitScript(user => {
      if (!sessionStorage.getItem("jurisdigta.web.auth.user.v1")) {
        sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
      }
      localStorage.setItem("aj_frontend_lang", "sk");
    }, auth.workflowUser);
    const source = await request.get(`${api}/v1/laws/document-text?document_id=${input.expectedLegalSourceId}`, {
      headers: headers(auth.workflowUser),
    });
    expect(source.ok()).toBe(true);
    expect(await source.text()).toContain(input.expectedLegalSourceId);
    await page.goto("/app/case");
    await page.getByLabel("Názov prípadu", { exact: true }).fill(input.caseTitle);
    await page.getByLabel("Protistrana", { exact: true }).fill("Bez protistrany – syntetický test");
    const creation = page.waitForResponse(r => r.url().endsWith("/v1/cases") && r.request().method() === "POST");
    await page.locator("form button[type=submit]").click();
    const created = await creation;
    expect(created.ok()).toBe(true);
    caseId = (await created.json()).case_id;
    await page.waitForURL("**/app/assistant");
    await page.goto(`/case/${caseId}`);
    const composer = page.locator(".assistant-composer__input");
    await expect(composer).toBeEnabled({ timeout: 60_000 });
    await composer.fill("Vysvetli všeobecne povinnosť vydať potvrdenie o splnení dlhu podľa § 569 zákona 40/1964 Z. z. Cituj dostupný zdroj. Nepripravuj dokument ani potvrdenie, ide len o vysvetlenie syntetického zdroja.");
    const streamPromise = page.waitForResponse(r => r.url().endsWith("/stream") && r.request().method() === "POST", { timeout: 60_000 });
    await page.locator(".assistant-composer__send").click();
    const stream = await streamPromise;
    expect(stream.ok()).toBe(true);
    const events = await stream.text();
    expect(events).toContain('"status": "generic"');
    await expect(page.locator(".assistant-message").last()).toBeVisible({ timeout: 180_000 });
    const diagnostics = await request.get(`${api}/v1/cases/${caseId}/diagnostics?user_id=${auth.workflowUser.userId}`, { headers: headers(auth.workflowUser) });
    expect(diagnostics.ok()).toBe(true);
    const correlation = (await diagnostics.json()).correlation_id;
    expect(correlation).toBeTruthy();
    const adminHeaders = { ...headers(auth.adminUser), "x-jurisdigta-admin-user-id": auth.adminUser.userId };
    const response = await request.get(`${api}/v1/admin/debug/${correlation}`, { headers: adminHeaders });
    expect(response.ok()).toBe(true);
    const debug = await response.json();
    const router = debug.langgraph_evidence.runs.find((run: { graph_key: string }) => run.graph_key === "primary_router");
    expect(router.run_status).toBe("completed");
    expect(router.topology_status).toBe("pinned");
    expect(router.occurrences.some((item: { node_id: string }) => item.node_id === "route_generic")).toBe(true);
    const models = debug.timeline.filter((event: { component: string; stage: string; status: string }) => event.component === "model" && event.stage === "completion" && event.status === "completed");
    expect(models.length).toBeGreaterThan(0);
    for (const model of models) {
      expect(model.payload.provider.toLowerCase()).toContain("azure");
      expect(model.payload.model).toBe(input.expectedModel);
    }
    expect(debug.timeline.some((event: { component: string; status: string }) => event.component === "mcp" && event.status === "completed")).toBe(true);
    const history = await request.get(`${api}/v1/cases/${caseId}/history?user_id=${auth.workflowUser.userId}`, { headers: headers(auth.workflowUser) });
    expect(history.ok()).toBe(true);
    const messages = (await history.json()).messages;
    const citations = messages.filter((m: { role: string }) => m.role === "assistant").flatMap((m: { citations?: Array<{ source_id: string }> }) => m.citations ?? []);
    expect(citations.some((c: { source_id: string }) => c.source_id === input.expectedLegalSourceId)).toBe(true);
    await page.evaluate(admin => sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(admin)), auth.adminUser);
    await page.goto("/app/admin");
    await page.getByRole("button", { name: "Ladenie", exact: true }).click();
    await page.getByLabel("ID korelácie").fill(correlation);
    await page.locator(".admin-debug__search button[type=submit]").click();
    await expect(page.getByRole("button", { name: "Celkový audit", exact: true })).toBeVisible();
    await expect(page.getByRole("img", { name: /primary_router/ })).toBeVisible();
    await expect(page.locator(".admin-debug__timeline")).toContainText("langgraph → graph_execution");
    await expect(page.locator(".admin-debug__timeline")).toContainText("model → completion");
    await expect(page.locator(".admin-debug__timeline")).toContainText("mcp → remote_tool_call");
    await expect(page.getByText(/historický beh/)).toHaveCount(0);
    await page.screenshot({ path: path.join(input.evidenceRoot, "full-audit-langgraph.png"), fullPage: true });
    const exported = await request.get(`${api}/v1/admin/debug/${correlation}/export`, { headers: adminHeaders });
    expect(exported.ok()).toBe(true);
    // Persist only sanitized metadata, never the protected full diagnostic export.
    await writeFile(path.join(input.evidenceRoot, "result-manifest.json"), JSON.stringify({
      passed: true, syntheticOnly: true, runId: input.runId, correlationId: correlation,
      caseId, provider: models.map((m: { payload: { provider: string; model: string } }) => ({ provider: m.payload.provider, model: m.payload.model })),
      services: ["frontend:5189", "api:8264", "mcp:8364", "loopback-postgresql"],
      expectedSourceIds: [input.expectedLegalSourceId], observedSourceIds: citations.map((c: { source_id: string }) => c.source_id),
      graphKey: router.graph_key, topologyDigest: router.topology_digest,
      observedNodes: router.occurrences.map((item: { node_id: string }) => item.node_id),
      retention: "Delete evidence within seven days; private authentication removed after test.",
    }, null, 2));
  } finally {
    if (caseId) {
      const deleted = await request.delete(`${api}/v1/cases/${caseId}?user_id=${auth.workflowUser.userId}`, { headers: headers(auth.workflowUser) });
      expect(deleted.ok()).toBe(true);
    }
    await rm(authPath, { force: true });
  }
});
