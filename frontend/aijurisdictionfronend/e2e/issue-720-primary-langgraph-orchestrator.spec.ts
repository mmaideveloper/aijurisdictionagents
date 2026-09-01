import { expect, test } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const apiBaseUrl = (process.env.ISSUE_720_API_BASE_URL ?? "http://127.0.0.1:8080").replace(/\/$/, "");
const apiKey = process.env.ISSUE_720_API_KEY ?? "aijuris";
const manifestInput = process.env.ISSUE_720_E2E_MANIFEST?.trim() ?? "";
const evidenceRoot = process.env.ISSUE_720_E2E_EVIDENCE?.trim() ?? "";
const enabled = Boolean(manifestInput && evidenceRoot);

type InputManifest = {
  syntheticOnly: true;
  runId: string;
  user: { userId: string; email: string; name: string };
  caseId: string;
  caseTitle: string;
  expectedProvider: string;
  expectedModel: string;
  expectedCaseType: string;
  expectedFlow: string;
  expectedLegalSourceId: string;
};

test.skip(!enabled, "Prepare real local services and set ISSUE_720_E2E_MANIFEST/EVIDENCE.");
test.setTimeout(900_000);

test("primary LangGraph uses generic routing then discovers a dedicated published flow", async ({ page, request }) => {
  const input = JSON.parse(await readFile(manifestInput, "utf8")) as InputManifest;
  expect(input.syntheticOnly).toBe(true);
  await mkdir(evidenceRoot, { recursive: true });
  await page.addInitScript((user) => {
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
    window.localStorage.setItem("aj_frontend_lang", "sk");
  }, input.user);
  await page.goto("/app/assistant", { waitUntil: "domcontentloaded" });
  await page.getByText(input.caseTitle, { exact: true }).click({ timeout: 60_000 });

  const genericStream = await submitTurn(
    page,
    input.caseTitle,
    "Vysvetli mi všeobecne zásadu proporcionality v práve bez prípravy dokumentu.",
  );
  expect(genericStream).toContain("langgraph_primary_router");
  expect(genericStream).toContain('"status": "generic"');
  await expect(page.locator(".assistant-message").last()).toBeVisible({ timeout: 180_000 });

  const headers = { "x-api-key": apiKey, Accept: "application/json" };
  const beforeDedicated = await request.get(
    `${apiBaseUrl}/v1/case-workflows/runs/latest?case_id=${encodeURIComponent(input.caseId)}&user_id=${encodeURIComponent(input.user.userId)}`,
    { headers },
  );
  expect(beforeDedicated.status()).toBe(404);

  await reloadSelectedCase(page, input.caseTitle);
  const dedicatedStream = await submitTurn(
    page,
    input.caseTitle,
    "Priprav mi potvrdenie o zaplatení pôžičky.",
  );
  expect(dedicatedStream).toContain("langgraph_case_workflow");
  expect(dedicatedStream).toContain("dedicated_case_workflow");

  let run: Record<string, unknown> = {};
  await expect
    .poll(
      async () => {
        const response = await request.get(
          `${apiBaseUrl}/v1/case-workflows/runs/latest?case_id=${encodeURIComponent(input.caseId)}&user_id=${encodeURIComponent(input.user.userId)}`,
          { headers },
        );
        if (!response.ok()) return false;
        run = (await response.json()) as Record<string, unknown>;
        const pending = (run.pending_action ?? {}) as Record<string, unknown>;
        return run.status === "waiting_for_user" && pending.field === "payer_identification";
      },
      { timeout: 360_000 },
    )
    .toBe(true);

  expect(run.case_type_key).toBe(input.expectedCaseType);
  expect(`${run.flow_key}@${run.flow_version}`).toBe(input.expectedFlow);
  const resumeTurns = [
    ["Syntetický Platiteľ A", "recipient_identification"],
    ["Syntetický Príjemca B", "amount"],
    ["100 EUR", "payment_date"],
    ["1. septembra 2026", "payment_purpose"],
    ["úplné splatenie syntetickej pôžičky", ""],
  ] as const;
  for (const [turn, expectedPendingField] of resumeTurns) {
    await reloadSelectedCase(page, input.caseTitle);
    await submitTurn(page, input.caseTitle, turn);
    await expect
      .poll(
        async () => {
          const response = await request.get(
            `${apiBaseUrl}/v1/case-workflows/runs/latest?case_id=${encodeURIComponent(input.caseId)}&user_id=${encodeURIComponent(input.user.userId)}`,
            { headers },
          );
          if (!response.ok()) return "unavailable";
          run = (await response.json()) as Record<string, unknown>;
          const pending = (run.pending_action ?? {}) as Record<string, unknown>;
          return `${String(run.status)}:${String(pending.field ?? "")}`;
        },
        { timeout: expectedPendingField ? 180_000 : 360_000 },
      )
      .toBe(
        expectedPendingField
          ? `waiting_for_user:${expectedPendingField}`
          : "completed:",
      );
  }

  const eventsResponse = await request.get(
    `${apiBaseUrl}/v1/case-workflows/runs/${encodeURIComponent(String(run.workflow_run_id))}/events?user_id=${encodeURIComponent(input.user.userId)}`,
    { headers },
  );
  expect(eventsResponse.ok()).toBeTruthy();
  const events = ((await eventsResponse.json()) as { items: Array<Record<string, unknown>> }).items;
  const routed = events.find((event) => event.event_type === "workflow_routed");
  expect(routed).toBeTruthy();
  const retrieval = events.find((event) => event.event_type === "legal_requirements_retrieved");
  expect(retrieval).toBeTruthy();
  const observedLegalSourceIds = String(
    ((retrieval?.details ?? {}) as Record<string, unknown>).source_ids ?? "",
  ).split(",").filter(Boolean);
  expect(observedLegalSourceIds).toContain(input.expectedLegalSourceId);

  const finalMessage = page.locator(".assistant-message").filter({ hasText: /ľudskú kontrolu/i }).last();
  await expect(finalMessage).toBeVisible({ timeout: 60_000 });
  await finalMessage.scrollIntoViewIfNeeded();
  const screenshotPath = path.join(evidenceRoot, "primary-langgraph-final.png");
  await page.screenshot({ path: screenshotPath, fullPage: true });

  const result = {
    schemaVersion: 1,
    scenarioId: "issue-720-primary-langgraph-orchestrator",
    runId: input.runId,
    syntheticOnly: true,
    services: ["frontend", "api", "mcp", "postgresql", "azure-foundry", "langgraph"],
    provider: input.expectedProvider,
    model: input.expectedModel,
    genericRouteObserved: true,
    dedicatedCaseType: run.case_type_key,
    graph: `${run.graph_key}@${run.graph_version}`,
    flow: `${run.flow_key}@${run.flow_version}`,
    workflowRunId: run.workflow_run_id,
    expectedLegalSourceId: input.expectedLegalSourceId,
    observedLegalSourceIds,
    observedEventIds: events.map((event) => event.event_id),
    screenshot: path.basename(screenshotPath),
    retention: "Delete ignored evidence within 7 days.",
  };
  await writeFile(path.join(evidenceRoot, "result-manifest.json"), `${JSON.stringify(result, null, 2)}\n`);

  const cleanup = await request.delete(
    `${apiBaseUrl}/v1/cases/${encodeURIComponent(input.caseId)}?user_id=${encodeURIComponent(input.user.userId)}`,
    { headers },
  );
  expect(cleanup.status()).toBe(204);
});

async function reloadSelectedCase(page: import("@playwright/test").Page, caseTitle: string) {
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByText(caseTitle, { exact: true }).click({ timeout: 60_000 });
}

async function submitTurn(
  page: import("@playwright/test").Page,
  caseTitle: string,
  value: string,
) {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const composer = page.locator(".assistant-composer__input");
    const send = page.locator(".assistant-composer__send");
    await expect(composer).toBeEnabled({ timeout: 60_000 });
    await composer.fill(value);
    await expect(send).toBeEnabled({ timeout: 30_000 });
    const streamResponse = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().includes("/v1/chat/sessions/") &&
        response.url().endsWith("/stream"),
      { timeout: 20_000 },
    );
    await send.click();
    const response = await streamResponse.catch(() => null);
    if (response?.ok()) return response.text();
    await reloadSelectedCase(page, caseTitle);
  }
  throw new Error(`Composer did not submit the reviewed turn: ${value}`);
}
