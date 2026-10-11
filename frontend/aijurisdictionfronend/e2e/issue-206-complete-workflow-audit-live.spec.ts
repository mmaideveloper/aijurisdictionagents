import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import { readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
const execFileAsync = promisify(execFile);

const fixture = path.resolve("../../runs/e2e/issue864");
const authPath = path.join(fixture, "private-auth.json");
const inputPath = path.join(fixture, "input-manifest.json");
const api = "http://127.0.0.1:8264";
test.skip(!existsSync(authPath) || !existsSync(inputPath), "Prepare the real #206 fixture and authenticate before this scenario.");
test.use({ viewport: { width: 1800, height: 1200 }, trace: "off", video: "off" });
test.setTimeout(900_000);

test("complete real workflow links output checks and retains a validated PDF", async ({ page, request }) => {
  const input = JSON.parse(await readFile(inputPath, "utf8"));
  const auth = JSON.parse(await readFile(authPath, "utf8"));
  expect(input.syntheticOnly).toBe(true);
  const userHeaders = { "x-api-key": "aijuris", "x-jurisdigta-device-id": auth.workflowUser.deviceId, "x-jurisdigta-device-token": auth.workflowUser.deviceAuthToken };
  const adminHeaders = { "x-api-key": "aijuris", "x-jurisdigta-device-id": auth.adminUser.deviceId, "x-jurisdigta-device-token": auth.adminUser.deviceAuthToken, "x-jurisdigta-admin-user-id": auth.adminUser.userId };
  let caseId = "";
  try {
    await page.addInitScript(user => {
      if (!sessionStorage.getItem("jurisdigta.web.auth.user.v1")) sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
      localStorage.setItem("aj_frontend_lang", "sk");
    }, auth.workflowUser);
    await page.goto("/app/case");
    await page.getByLabel("Názov prípadu", { exact: true }).fill(`${input.caseTitle} resume`);
    await page.getByLabel("Protistrana", { exact: true }).fill("Syntetická protistrana");
    const [created] = await Promise.all([
      page.waitForResponse(r => r.url().endsWith("/v1/cases") && r.request().method() === "POST"),
      page.locator("form button[type=submit]").click(),
    ]);
    expect(created.ok()).toBe(true);
    caseId = (await created.json()).case_id;
    await page.waitForURL("**/app/assistant");
    async function send(text: string) {
      await page.goto(`/case/${caseId}`);
      await page.waitForLoadState("networkidle");
      const composer = page.locator(".assistant-composer__input");
      await expect(async () => {
        await expect(composer).toBeEnabled();
        await composer.fill(text);
        await expect(composer).toHaveValue(text);
        await expect(page.locator(".assistant-composer__send")).toBeEnabled();
      }).toPass({ timeout: 60_000 });
      const [response] = await Promise.all([
        page.waitForResponse(r => r.url().endsWith("/stream") && r.request().method() === "POST", { timeout: 60_000 }),
        page.locator(".assistant-composer__send").click(),
      ]);
      expect(response.ok()).toBe(true);
      await response.text();
      return { requestId: response.request().headers()["x-request-id"], correlationId: response.request().headers()["x-correlation-id"] };
    }
    async function latest() {
      const response = await request.get(`${api}/v1/case-workflows/runs/latest`, { headers: userHeaders, params: { case_id: caseId, user_id: auth.workflowUser.userId } });
      expect(response.ok()).toBe(true);
      return response.json();
    }
    const firstRequest = await send("Priprav mi potvrdenie o zaplatení pôžičky.");
    await expect.poll(async () => (await latest()).status, { timeout: 180_000 }).toBe("waiting_for_user");
    const firstRun = await latest();
    expect(firstRun.pending_action.field).toBe("payer_identification");
    const secondRequest = await send("Syntetický Platiteľ A");
    expect(secondRequest.requestId).not.toBe(firstRequest.requestId);
    await expect.poll(async () => (await latest()).pending_action.field, { timeout: 180_000 }).toBe("recipient_identification");
    const remainingRequests = [];
    for (const answer of ["Syntetický Príjemca B", "100 EUR", "11. októbra 2026", "úplné splatenie syntetickej pôžičky"]) remainingRequests.push(await send(answer));
    const afterFacts = await latest();
    const declinedOptionalTool = afterFacts.pending_action?.type === "tool_consent";
    if (declinedOptionalTool) remainingRequests.push(await send("Nesúhlasím"));
    await expect.poll(async () => (await latest()).status, { timeout: 180_000 }).toBe("completed");
    const run = await latest();
    expect(run.workflow_run_id).toBe(firstRun.workflow_run_id);
    expect(run.graph_version).toBe(firstRun.graph_version);
    expect(run.flow_version).toBe(firstRun.flow_version);
    const eventResponse = await request.get(`${api}/v1/case-workflows/runs/${run.workflow_run_id}/events`, { headers: userHeaders, params: { user_id: auth.workflowUser.userId } });
    expect(eventResponse.ok()).toBe(true);
    const events = (await eventResponse.json()).items;
    if (declinedOptionalTool) {
      expect(events.some((event: { event_type: string; details: { decision?: string } }) => event.event_type === "tool_consent_recorded" && event.details.decision === "denied")).toBe(true);
    }
    const observedSourceIds = events.filter((event: { event_type: string }) => event.event_type === "legal_requirements_retrieved")
      .flatMap((event: { details: { source_ids: string[] } }) => event.details.source_ids);
    expect(observedSourceIds).toContain(input.expectedLegalSourceId);
    expect(events.some((event: { event_type: string }) => event.event_type === "workflow_resumed")).toBe(true);
    expect(events.filter((event: { event_type: string }) => event.event_type === "workflow_interrupted").length).toBeGreaterThanOrEqual(2);
    const response = await request.get(`${api}/v1/admin/debug/${run.correlation_id}`, { headers: adminHeaders });
    expect(response.ok()).toBe(true);
    const debug = await response.json();
    const correlations = [...new Set([run.correlation_id, firstRequest.correlationId, secondRequest.correlationId, ...remainingRequests.map(item => item.correlationId)])];
    const traces = [];
    for (const correlation of correlations) {
      const retained = await request.get(`${api}/v1/admin/debug/${correlation}`, { headers: adminHeaders });
      expect(retained.ok()).toBe(true);
      traces.push(await retained.json());
    }
    const search = await request.get(`${api}/v1/admin/debug`, { headers: adminHeaders, params: { case_id: caseId, user_id: auth.workflowUser.userId } });
    expect(search.ok()).toBe(true);
    const indexed = (await search.json()).items.map((item: { correlation_id: string }) => item.correlation_id);
    for (const correlation of correlations) expect(indexed).toContain(correlation);
    const graph = debug.langgraph_evidence.runs.find((item: { workflow_run_id: string }) => item.workflow_run_id === run.workflow_run_id);
    expect(graph).toBeTruthy();
    expect(graph.topology_status).toBe("pinned");
    expect(new Set(graph.occurrences.map((item: { event_id: string }) => item.event_id)).size).toBe(graph.occurrences.length);
    const checks = traces.flatMap(trace => trace.validation_evidence.checks).filter((item: { category: string }) => item.category === "input_structure");
    expect(checks.length).toBeGreaterThanOrEqual(2);
    expect(new Set(checks.map((item: { execution_id: string }) => item.execution_id)).size).toBe(checks.length);
    expect(checks.some((item: { outcome: string }) => item.outcome === "failed")).toBe(true);
    expect(checks.some((item: { outcome: string }) => item.outcome === "passed")).toBe(true);
    const linkedChecks = traces.flatMap(trace => trace.langgraph_evidence.runs).filter((item: { workflow_run_id: string }) => item.workflow_run_id === run.workflow_run_id)
      .flatMap(item => item.occurrences).filter((item: { node_id: string }) => item.node_id === "verify_input")
      .flatMap(item => item.execution_evidence ?? []).filter((item: { component: string }) => item.component === "validation");
    for (const check of checks) expect(linkedChecks.some((item: { execution_id: string }) => item.execution_id === check.execution_id)).toBe(true);
    for (const stage of ["verify_output", "verify_safety_and_gdpr"]) {
      const node = graph.occurrences.find((item: { node_id: string }) => item.node_id === stage);
      expect(node).toBeTruthy();
      const evidence = node.execution_evidence.filter((item: { component: string }) => item.component === "validation");
      expect(evidence.length).toBeGreaterThan(0);
      expect(evidence.every((item: { artifact_id: string; status: string }) => !!item.artifact_id && item.status === "passed")).toBe(true);
    }
    const artifact = run.artifacts[0];
    expect(artifact).toBeTruthy();
    const pdfResponse = await request.get(`${api}/v1/case-workflows/runs/${run.workflow_run_id}/artifacts/${artifact.artifact_id}/pdf`, { headers: userHeaders, params: { user_id: auth.workflowUser.userId } });
    expect(pdfResponse.ok()).toBe(true);
    const pdfPath = path.join(input.evidenceRoot, "issue-206-complete-workflow.pdf");
    await writeFile(pdfPath, await pdfResponse.body());
    const pdf = await renderAndValidatePdf(pdfPath, path.join(input.evidenceRoot, "issue-206-complete-workflow-first-page.png"));
    expect(pdf.pageCount).toBeGreaterThan(0);
    expect(pdf.extractedText).toContain("100 EUR");
    expect(pdf.extractedText).toContain("ľudskú kontrolu");
    await page.screenshot({ path: path.join(input.evidenceRoot, "issue-206-complete-workflow-user.png"), fullPage: true });
    const models = traces.flatMap(trace => trace.timeline).filter((item: { component: string; stage: string; status: string }) => item.component === "model" && item.stage === "completion" && item.status === "completed");
    expect(models.length).toBeGreaterThan(0);
    expect(models.every((item: { payload: { provider: string; model: string } }) => item.payload.provider.includes("azure") && item.payload.model === input.expectedModel)).toBe(true);
    await page.evaluate(admin => sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(admin)), auth.adminUser);
    await page.goto("/app/admin");
    await page.getByRole("button", { name: "Ladenie", exact: true }).click();
    await page.getByLabel("ID korelácie").fill(run.correlation_id);
    await page.getByRole("button", { name: "Otvoriť presnú koreláciu", exact: true }).click();
    await expect(page.getByRole("img", { name: /legal_document_workflow/ })).toBeVisible();
    await expect(page.getByRole("region", { name: "Pokrytie auditnými dôkazmi" })).toContainText("required_facts");
    await page.locator(".langgraph-audit__execution-list button").filter({ hasText: "verify_input" }).first().click();
    await expect(page.locator(".langgraph-audit__details")).toContainText("required_facts");
    await page.screenshot({ path: path.join(input.evidenceRoot, "issue-206-complete-workflow-audit.png"), fullPage: true });
    await writeFile(path.join(input.evidenceRoot, "complete-workflow-result-manifest.json"), JSON.stringify({ passed: true, syntheticOnly: true, runId: input.runId, workflowRunId: run.workflow_run_id, graphVersion: run.graph_version, flowVersion: run.flow_version, pdfValidated: true, pdfPages: pdf.pageCount, expectedSourceIds: [input.expectedLegalSourceId], observedSourceIds, requests: [firstRequest, secondRequest, ...remainingRequests], correlationIds: correlations, validatorExecutionIds: checks.map((item: { execution_id: string }) => item.execution_id), provider: "azurefoundry", model: input.expectedModel, services: ["frontend:5189", "api:8264", "mcp:8364", "loopback-postgresql"], retention: "Seven days maximum" }, null, 2));
  } finally {
    try {
      if (caseId) expect((await request.delete(`${api}/v1/cases/${caseId}`, { headers: userHeaders, params: { user_id: auth.workflowUser.userId } })).ok()).toBe(true);
    } finally { await rm(authPath, { force: true }); }
  }
});

async function renderAndValidatePdf(pdfPath: string, firstPagePath: string) {
  const python = process.env.PYTHON ?? path.resolve(process.cwd(), "../../conda/python.exe");
  const script = [
    "import fitz, json, sys",
    "from pypdf import PdfReader",
    "pdf_path, png_path = sys.argv[1], sys.argv[2]",
    "reader = PdfReader(pdf_path)",
    "text = '\\n'.join((page.extract_text() or '') for page in reader.pages)",
    "doc = fitz.open(pdf_path)",
    "doc[0].get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(png_path)",
    "print(json.dumps({'pageCount': len(reader.pages), 'extractedText': text}, ensure_ascii=False))",
  ].join("\n");
  const { stdout } = await execFileAsync(python, ["-c", script, pdfPath, firstPagePath], {
    encoding: "utf8",
    env: { ...process.env, PYTHONIOENCODING: "utf-8" },
  });
  const jsonLine = stdout
    .trim()
    .split(/\r?\n/)
    .reverse()
    .find((line) => line.trimStart().startsWith("{"));
  if (!jsonLine) throw new Error("PDF validation did not emit a JSON result.");
  return JSON.parse(jsonLine) as { pageCount: number; extractedText: string };
}
