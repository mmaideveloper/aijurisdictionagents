import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";

const directory = path.resolve("../../runs/e2e/issue864");
const manifestPath = path.join(directory, "input-manifest.json");
const authPath = path.join(directory, "private-auth.json");
const api = "http://127.0.0.1:8264";
test.skip(!existsSync(manifestPath) || !existsSync(authPath), "Run scripts/audit_e2e_206.py setup, prepare, services and authenticate first.");
test.use({ viewport: { width: 1800, height: 1200 }, trace: "off", video: "off" });
test.setTimeout(600_000);

test("two real frontend turns retain separate causal paths and audit evidence", async ({ page, request }) => {
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
    // Initial case hydration can replace the assistant runtime; finish it before sending.
    await page.waitForLoadState("networkidle");
    await expect(page.getByLabel("AI model použitý pre tento chat")).toContainText(input.expectedModel);
    const composer = page.locator(".assistant-composer__input");
    await expect(composer).toBeEnabled({ timeout: 60_000 });
    await composer.fill("Ako sa číta označenie § 569 ods. 1 zákona 40/1964 Z. z. v právnej citácii? Vysvetli význam paragrafu, odseku a čísla zákona s citáciou dostupného zdroja.");
    const streamPromise = page.waitForResponse(r => r.url().endsWith("/stream") && r.request().method() === "POST", { timeout: 60_000 });
    await page.locator(".assistant-composer__send").click();
    const stream = await streamPromise;
    expect(stream.ok()).toBe(true);
    const events = await stream.text();
    expect(events).toContain('"status": "generic"');
    await expect(page.locator(".assistant-message").last()).toBeVisible({ timeout: 180_000 });
    await page.waitForLoadState("networkidle");
    await expect(composer).toBeEnabled({ timeout: 180_000 });
    const secondPrompt = "Vysvetli ešte raz stručne rozdiel medzi paragrafom a odsekom v tej istej citácii § 569 ods. 1 zákona 40/1964 Z. z. s dostupným zdrojom.";
    await expect(async () => {
      await composer.fill(secondPrompt);
      await expect(composer).toHaveValue(secondPrompt);
      await expect(page.locator(".assistant-composer__send")).toBeEnabled();
    }).toPass({ timeout: 30_000 });
    const [secondStream] = await Promise.all([
      page.waitForResponse(r => r.url().endsWith("/stream") && r.request().method() === "POST", { timeout: 60_000 }),
      page.locator(".assistant-composer__send").click(),
    ]);
    expect(secondStream.ok()).toBe(true);
    await secondStream.text();
    const diagnostics = await request.get(`${api}/v1/cases/${caseId}/diagnostics?user_id=${auth.workflowUser.userId}`, { headers: headers(auth.workflowUser) });
    expect(diagnostics.ok()).toBe(true);
    const correlation = (await diagnostics.json()).correlation_id;
    expect(correlation).toBeTruthy();
    const adminHeaders = { ...headers(auth.adminUser), "x-jurisdigta-admin-user-id": auth.adminUser.userId };
    const response = await request.get(`${api}/v1/admin/debug/${correlation}`, { headers: adminHeaders });
    expect(response.ok()).toBe(true);
    const debug = await response.json();
    const firstCorrelation = stream.request().headers()["x-correlation-id"];
    expect(firstCorrelation).toBeTruthy();
    const firstResponse = await request.get(`${api}/v1/admin/debug/${firstCorrelation}`, { headers: adminHeaders });
    expect(firstResponse.ok()).toBe(true);
    const firstDebug = await firstResponse.json();
    const traces = firstCorrelation === correlation ? [debug] : [firstDebug, debug];
    expect(debug.decision_evidence.engine).toBe("langgraph");
    expect(debug.decision_evidence.model_supplied_summary_status).toBe("unavailable");
    expect(debug.session.id).toBeTruthy();
    const search = await request.get(`${api}/v1/admin/debug`, { headers: adminHeaders, params: {
      user_id: auth.workflowUser.userId, case_id: caseId, session_id: debug.session.id, correlation_id: correlation,
    } });
    expect(search.ok()).toBe(true);
    expect((await search.json()).items.some((item: { correlation_id: string }) => item.correlation_id === correlation)).toBe(true);
    const unrelated = await request.get(`${api}/v1/admin/debug`, { headers: adminHeaders, params: {
      user_id: auth.adminUser.userId, case_id: caseId,
    } });
    expect(unrelated.ok()).toBe(true);
    expect((await unrelated.json()).items).toHaveLength(0);
    const caseSearch = await request.get(`${api}/v1/admin/debug`, { headers: adminHeaders, params: { user_id: auth.workflowUser.userId, case_id: caseId } });
    expect(caseSearch.ok()).toBe(true);
    const caseCorrelations = (await caseSearch.json()).items.map((item: { correlation_id: string }) => item.correlation_id);
    expect(caseCorrelations).toContain(firstCorrelation);
    expect(caseCorrelations).toContain(correlation);
    expect(debug.flow.edge_basis).toBe("recorded_parent_request_id");
    const httpRequest = stream.request().headers()["x-request-id"];
    expect(httpRequest).toBeTruthy();
    const worker = firstDebug.flow.nodes.find((node: { parent_request_id: string; observations: Array<{ stage: string }> }) =>
      node.parent_request_id === httpRequest && node.observations.some(item => item.stage === "chat_session_worker"));
    expect(worker).toBeTruthy();
    expect(worker.id).not.toBe(httpRequest);
    expect(firstDebug.flow.edges).toContainEqual({ from: httpRequest, to: worker.id });
    const secondHttp = secondStream.request().headers()["x-request-id"];
    expect(secondHttp).not.toBe(httpRequest);
    const secondWorker = debug.flow.nodes.find((node: { parent_request_id: string; observations: Array<{ stage: string }> }) => node.parent_request_id === secondHttp && node.observations.some(item => item.stage === "chat_session_worker"));
    expect(secondWorker).toBeTruthy();
    expect(secondWorker.id).not.toBe(worker.id);
    expect(debug.flow.edges).toContainEqual({ from: secondHttp, to: secondWorker.id });
    expect(debug.validation_evidence.categories).toHaveLength(6);
    expect(debug.validation_evidence.categories.find((item: { category: string }) => item.category === "hallucination_assessment").evidence_status).toBe("missing_evidence");
    const provenance = debug.timeline.filter((event: { component: string; stage: string; status: string; payload: { route_provenance?: unknown } }) => event.component === "model" && event.stage === "completion" && event.status === "started" && event.payload.route_provenance);
    expect(provenance.length).toBeGreaterThan(0);
    expect(provenance.some((event: { payload: { route_provenance: { model_profile_id: string } } }) => !!event.payload.route_provenance.model_profile_id)).toBe(true);
    for (const trace of traces) {
      const operations = new Map(trace.flow.nodes.map((node: { id: string }) => [node.id, node]));
      for (const edge of trace.flow.edges) {
        expect(operations.has(edge.from)).toBe(true);
        expect(operations.has(edge.to)).toBe(true);
        expect(trace.timeline.some((event: { request_id: string; parent_request_id: string }) =>
          event.request_id === edge.to && event.parent_request_id === edge.from)).toBe(true);
      }
    }
    const rejected = await request.get(`${api}/v1/admin/debug/${correlation}`, { headers: headers(auth.workflowUser) });
    expect([401, 403]).toContain(rejected.status());
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
    // History messages are paginated; the response's citation collection covers the whole case.
    const citations = (await history.json()).citations ?? [];
    expect(citations.some((c: { source_id: string }) => c.source_id === input.expectedLegalSourceId)).toBe(true);
    await page.evaluate(admin => sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(admin)), auth.adminUser);
    await page.goto("/app/admin");
    await page.getByRole("button", { name: "Ladenie", exact: true }).click();
    await page.getByLabel("ID korelácie").fill(correlation);
    await page.getByRole("button", { name: "Otvoriť presnú koreláciu", exact: true }).click();
    await expect(page.getByRole("button", { name: "Celkový audit", exact: true })).toBeVisible();
    await expect(page.getByRole("img", { name: /primary_router/ })).toBeVisible();
    await expect(page.locator(".admin-debug__timeline")).toContainText("langgraph → graph_execution");
    await expect(page.locator(".admin-debug__timeline")).toContainText("model → completion");
    await expect(page.locator(".admin-debug__timeline")).toContainText("mcp → remote_tool_call");
    await expect(page.getByText(/historický beh/)).toHaveCount(0);
    await page.getByRole("button", { name: "Tok", exact: true }).click();
    await expect(page.getByRole("region", { name: "Pokrytie auditnými dôkazmi" })).toContainText("Posúdenie halucinácií");
    await expect(page.getByRole("region", { name: "Pokrytie auditnými dôkazmi" })).toContainText("Chýbajúce dôkazy");
    await expect(page.getByText("Zaznamenaná nadradená operácia", { exact: false }).first()).toBeVisible();
    await page.screenshot({ path: path.join(input.evidenceRoot, "issue-206-real-causal-flow.png"), fullPage: true });
    const exported = await request.get(`${api}/v1/admin/debug/${correlation}/export`, { headers: adminHeaders });
    expect(exported.ok()).toBe(true);
    // Persist only sanitized metadata, never the protected full diagnostic export.
    await writeFile(path.join(input.evidenceRoot, "result-manifest.json"), JSON.stringify({
      passed: true, issue: 206, httpRequestIds: [httpRequest, secondHttp], workerRequestIds: [worker.id, secondWorker.id], causalTraces: traces.map(trace => ({ correlationId: trace.correlation_id, edges: trace.flow.edges })), syntheticOnly: true, runId: input.runId, correlationId: correlation,
      validationCategories: debug.validation_evidence.categories,
      provenance: provenance.map((event: { request_id: string; payload: { route_provenance: { model_profile_id: string; policy_digest: string; reason_code: string } } }) => ({ requestId: event.request_id, modelProfile: event.payload.route_provenance.model_profile_id, policyDigest: event.payload.route_provenance.policy_digest, reasonCode: event.payload.route_provenance.reason_code })),
      caseId, provider: models.map((m: { payload: { provider: string; model: string } }) => ({ provider: m.payload.provider, model: m.payload.model })),
      services: ["frontend:5189", "api:8264", "mcp:8364", "loopback-postgresql"],
      expectedSourceIds: [input.expectedLegalSourceId], observedSourceIds: citations.map((c: { source_id: string }) => c.source_id),
      graphKey: router.graph_key, topologyDigest: router.topology_digest,
      observedNodes: router.occurrences.map((item: { node_id: string }) => item.node_id),
      retention: "Delete evidence within seven days; private authentication removed after test.",
    }, null, 2));
  } finally {
    try {
      if (caseId) {
        const deleted = await request.delete(`${api}/v1/cases/${caseId}?user_id=${auth.workflowUser.userId}`, { headers: headers(auth.workflowUser) });
        expect(deleted.ok()).toBe(true);
      }
    } finally {
      await rm(authPath, { force: true });
    }
  }
});
