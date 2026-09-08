import { expect, test } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const apiBaseUrl = (process.env.ISSUE_788_API_BASE_URL ?? "http://127.0.0.1:8080").replace(/\/$/, "");
const apiKey = process.env.ISSUE_788_API_KEY ?? "aijuris";
const manifestInput = process.env.ISSUE_788_E2E_MANIFEST?.trim() ?? "";
const evidenceRoot = process.env.ISSUE_788_E2E_EVIDENCE?.trim() ?? "";
const enabled = Boolean(manifestInput && evidenceRoot);

type InputManifest = {
  syntheticOnly: true;
  runId: string;
  correlationId: string;
  sessionId: string;
  workflowUser: { userId: string; email: string };
  adminUser: { userId: string; email: string; name: string; role: "admin"; isEnabled: true };
  caseId: string;
  expectedProvider: string;
  expectedModel: string;
};

test.skip(!enabled, "Prepare real local services and set ISSUE_788_E2E_MANIFEST/EVIDENCE.");
test.setTimeout(600_000);

test("real workflow renders its pinned LangGraph and execution evidence for audit", async ({ page, request }) => {
  const input = JSON.parse(await readFile(manifestInput, "utf8")) as InputManifest;
  expect(input.syntheticOnly).toBe(true);
  await mkdir(evidenceRoot, { recursive: true });
  const headers = { "x-api-key": apiKey, Accept: "application/json" };
  const started = await request.post(`${apiBaseUrl}/v1/case-workflows/runs`, {
    headers,
    data: {
      case_id: input.caseId,
      session_id: input.sessionId,
      user_id: input.workflowUser.userId,
      jurisdiction: "SK",
      case_type_key: "sk.civil.payment_confirmation",
      request_text: "Prepare a synthetic payment confirmation for the issue 788 audit test.",
      language: "en",
      routing_confidence: 1,
      routing_evidence: ["issue-788 deterministic E2E selection"],
      facts: {
        payer_identification: "Synthetic Payer A",
        recipient_identification: "Synthetic Recipient B",
        amount: "100 EUR",
        payment_date: "8 September 2026",
        payment_purpose: "Synthetic loan repayment"
      },
      external_provider_acknowledged: true,
      correlation_id: input.correlationId
    }
  });
  expect(started.ok(), await started.text()).toBeTruthy();
  const workflow = await started.json() as Record<string, unknown>;
  expect(workflow.status).toBe("completed");

  await page.addInitScript((admin) => {
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(admin));
    window.localStorage.setItem("aj_frontend_lang", "en");
  }, input.adminUser);
  await page.goto("/app/admin", { waitUntil: "domcontentloaded" });
  const debugNavigation = page.getByRole("button", { name: "Debug" });
  await expect(debugNavigation).toBeVisible({ timeout: 20_000 });
  await debugNavigation.click();
  await page.getByLabel("Correlation ID").fill(input.correlationId);
  await page.getByRole("button", { name: "Search logs" }).click();
  const langGraphTab = page.getByRole("button", { name: "LangGraph audit" });
  await expect(langGraphTab).toBeVisible({ timeout: 20_000 });
  await langGraphTab.click();

  const runSelector = page.getByLabel("Workflow run");
  await runSelector.selectOption(String(workflow.workflow_run_id));
  await expect(runSelector).toHaveValue(String(workflow.workflow_run_id));
  await expect(page.getByText(`${workflow.graph_key}@${workflow.graph_version}`).last()).toBeVisible();
  await expect(page.getByText(/Topology SHA-256: [a-f0-9]{64}/)).toBeVisible();
  await expect(page.getByRole("img", { name: /executable graph with recorded execution overlay/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Ordered execution evidence" })).toBeVisible();
  await expect(page.getByText("Transition not recorded")).toHaveCount(0);
  const executionItems = page.locator(".langgraph-audit__execution-list li");
  expect(await executionItems.count()).toBeGreaterThan(5);
  const recordedNode = page.getByRole("button", { name: /Route Case Type: recorded execution/ });
  await expect(recordedNode).toBeVisible({ timeout: 20_000 });
  await recordedNode.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText(/recorded occurrence/)).toBeVisible();

  const debugResponse = await request.get(
    `${apiBaseUrl}/v1/admin/debug/${encodeURIComponent(input.correlationId)}`,
    { headers: { ...headers, "x-jurisdigta-admin-user-id": input.adminUser.userId } }
  );
  expect(debugResponse.ok()).toBeTruthy();
  const debug = await debugResponse.json() as Record<string, unknown>;
  const graphEvidence = debug.langgraph_evidence as { runs: Array<Record<string, unknown>> };
  const auditedRun = graphEvidence.runs.find((item) => item.workflow_run_id === workflow.workflow_run_id)!;
  expect(auditedRun.topology_status).toBe("pinned");
  expect(auditedRun.evidence_completeness).toBe("complete");

  const screenshot = path.join(evidenceRoot, "admin-langgraph-audit.png");
  await page.screenshot({ path: screenshot, fullPage: true });
  await writeFile(path.join(evidenceRoot, "langgraph-evidence.json"), `${JSON.stringify(debug.langgraph_evidence, null, 2)}\n`);
  await writeFile(path.join(evidenceRoot, "result-manifest.json"), `${JSON.stringify({
    schemaVersion: 1,
    scenarioId: "issue-788-langgraph-audit",
    runId: input.runId,
    syntheticOnly: true,
    services: ["frontend", "api", "mcp", "postgresql", "azure-foundry"],
    provider: input.expectedProvider,
    model: input.expectedModel,
    workflowRunId: workflow.workflow_run_id,
    correlationId: input.correlationId,
    graph: `${workflow.graph_key}@${workflow.graph_version}`,
    flow: `${workflow.flow_key}@${workflow.flow_version}`,
    topologyDigest: auditedRun.topology_digest,
    observedEventIds: (auditedRun.occurrences as Array<Record<string, unknown>>).map((item) => item.event_id),
    screenshot: path.basename(screenshot),
    retention: "Delete ignored evidence within 7 days."
  }, null, 2)}\n`);

  const cleanup = await request.delete(
    `${apiBaseUrl}/v1/cases/${encodeURIComponent(input.caseId)}?user_id=${encodeURIComponent(input.workflowUser.userId)}`,
    { headers, timeout: 10_000 }
  );
  expect([204, 404]).toContain(cleanup.status());
});
