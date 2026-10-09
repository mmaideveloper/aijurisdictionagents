import { expect, test } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

// Reuse the existing synthetic PostgreSQL + real-model audit fixture and environment contract.
const manifestPath = process.env.ISSUE_788_E2E_MANIFEST?.trim() ?? "";
const evidenceRoot = process.env.ISSUE_788_E2E_EVIDENCE?.trim() ?? "";
const api = (process.env.ISSUE_788_API_BASE_URL ?? "http://127.0.0.1:8080").replace(/\/$/, "");
test.skip(!manifestPath || !evidenceRoot, "Prepare the real-local audit fixture; this is never replaced with mocked data.");
test.setTimeout(600_000);

test("real PostgreSQL audit search resolves all identifiers and selects the same trace", async ({ page, request }, testInfo) => {
  const input = JSON.parse(await readFile(manifestPath, "utf8")) as {
    syntheticOnly: boolean; database: string; runId: string; correlationId: string; sessionId: string;
    caseId: string; workflowUser: { userId: string };
    adminUser: { userId: string }; expectedProvider: string; expectedModel: string;
  };
  expect(input.syntheticOnly).toBe(true);
  expect(input.database).toBe("loopback-postgresql");
  expect(input.expectedProvider).not.toBe("mock");
  expect(["127.0.0.1", "localhost"]).toContain(new URL(api).hostname);
  const headers = { "x-api-key": process.env.ISSUE_788_API_KEY ?? "aijuris" };
  const adminHeaders = { ...headers, "x-jurisdigta-admin-user-id": input.adminUser.userId };
  const evidence = path.join(evidenceRoot, "issue-855");
  await mkdir(evidence, { recursive: true });
  try {
    const started = await request.post(`${api}/v1/case-workflows/runs`, { headers, data: {
      case_id: input.caseId, session_id: input.sessionId, user_id: input.workflowUser.userId,
      correlation_id: input.correlationId, jurisdiction: "SK", case_type_key: "sk.civil.payment_confirmation",
      request_text: "Prepare a synthetic payment confirmation for the audit search test.", language: "en",
      routing_confidence: 1, routing_evidence: ["synthetic-audit-search"], external_provider_acknowledged: true,
      facts: { payer_identification: "Synthetic Payer A", recipient_identification: "Synthetic Recipient B",
        amount: "100 EUR", payment_date: "7 October 2026", payment_purpose: "Synthetic loan repayment" }
    } });
    expect(started.ok()).toBeTruthy();
    const run = await started.json() as { status: string; workflow_run_id: string };
    expect(run.status).toBe("completed");
    const identifiers = { user_id: input.workflowUser.userId, case_id: input.caseId,
      session_id: input.sessionId, correlation_id: input.correlationId };
    for (const [key, value] of Object.entries(identifiers)) {
      const found = await request.get(`${api}/v1/admin/debug?${new URLSearchParams({ [key]: value })}`, { headers: adminHeaders });
      expect(found.ok()).toBeTruthy();
      expect((await found.json()).items).toEqual(expect.arrayContaining([expect.objectContaining(identifiers)]));
    }
    const excluded = await request.get(`${api}/v1/admin/debug?${new URLSearchParams({ ...identifiers, user_id: "unrelated-synthetic-user" })}`, { headers: adminHeaders });
    expect(excluded.ok()).toBeTruthy();
    expect((await excluded.json()).items).toEqual([]);
    const debug = await request.get(`${api}/v1/admin/debug/${input.correlationId}`, { headers: adminHeaders });
    expect(debug.ok()).toBeTruthy();
    const observed = await debug.json() as { decision_traces: Array<{
      provider_id: string; model_id: string; evidence: Array<{ evidence_type: string; reference_id: string }>
    }> };
    const sourceIds = [...new Set(observed.decision_traces.flatMap((row) => row.evidence
      .filter((item) => item.evidence_type === "legal_source").map((item) => item.reference_id)))];
    expect(sourceIds).toContain("issue-635-civil-code");
    expect(observed.decision_traces).toEqual(expect.arrayContaining([expect.objectContaining({
      provider_id: input.expectedProvider, model_id: input.expectedModel
    })]));
    await page.addInitScript((admin) => {
      sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(admin));
      localStorage.setItem("aj_frontend_lang", "en");
    }, input.adminUser);
    await page.goto("/app/admin");
    await page.getByRole("button", { name: "Debug", exact: true }).click();
    await page.getByLabel("User ID", { exact: true }).fill(input.workflowUser.userId);
    await page.getByLabel("Case ID", { exact: true }).fill(input.caseId);
    await page.getByRole("button", { name: "Search logs" }).click();
    await page.getByRole("button", { name: input.correlationId, exact: true }).click();
    await expect(page.getByRole("button", { name: "LangGraph audit" })).toBeVisible();
    const screenshot = path.join(evidence, "issue-855-real-search-selected-trace.png");
    await page.setViewportSize({ width: 1600, height: 1200 });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: screenshot, fullPage: true });
    await testInfo.attach("Real local audit search", { path: screenshot, contentType: "image/png" });
    await writeFile(path.join(evidence, "result-manifest.json"), JSON.stringify({
      runId: input.runId, syntheticOnly: true, services: ["frontend", "api", "mcp", "postgresql", "azure-foundry"],
      expectedRoute: { provider: input.expectedProvider, model: input.expectedModel },
      observedRoutes: [...new Set(observed.decision_traces.filter((row) => row.provider_id).map((row) => `${row.provider_id}/${row.model_id}`))],
      expectedSourceIds: ["issue-635-civil-code"], observedSourceIds: sourceIds,
      identifiers, screenshot: path.basename(screenshot), retention: "Delete within seven days."
    }, null, 2));
  } finally {
    const cleaned = await request.delete(`${api}/v1/cases/${input.caseId}?user_id=${input.workflowUser.userId}`, { headers });
    expect([204, 404]).toContain(cleaned.status());
  }
});
