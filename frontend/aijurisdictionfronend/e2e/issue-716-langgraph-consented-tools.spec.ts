import { expect, test } from "@playwright/test";
import { execFile } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const apiBaseUrl = (process.env.ISSUE_716_API_BASE_URL ?? "http://127.0.0.1:8080").replace(/\/$/, "");
const apiKey = process.env.ISSUE_716_API_KEY ?? "aijuris";
const manifestInput = process.env.ISSUE_716_E2E_MANIFEST?.trim() ?? "";
const evidenceRoot = process.env.ISSUE_716_E2E_EVIDENCE?.trim() ?? "";
const enabled = Boolean(manifestInput && evidenceRoot);

type InputManifest = {
  syntheticOnly: true;
  runId: string;
  user: { userId: string; email: string; name: string };
  caseId: string;
  caseTitle: string;
  expectedProvider: string;
  expectedModel: string;
  expectedTool: string;
  expectedConsentScope: string;
  expectedConsentTextVersion: string;
  expectedLegalSourceId: string;
};

test.skip(!enabled, "Prepare real local services and set ISSUE_716_E2E_MANIFEST/EVIDENCE.");
test.setTimeout(900_000);

test("real LangGraph model proposal requires consent and executes the address tool", async ({ page, request }) => {
  const input = JSON.parse(await readFile(manifestInput, "utf8")) as InputManifest;
  expect(input.syntheticOnly).toBe(true);
  await mkdir(evidenceRoot, { recursive: true });
  await page.addInitScript((user) => {
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
    window.localStorage.setItem("aj_frontend_lang", "sk");
  }, input.user);
  await page.goto("/app/assistant", { waitUntil: "domcontentloaded" });
  await page.getByText(input.caseTitle, { exact: true }).click({ timeout: 60_000 });

  const turns = [
    "Priprav mi potvrdenie o zaplatení a over adresu príjemcu cez registeradries.",
    "Syntetický Platiteľ A",
    "Testovacia 1, 811 01 Bratislava",
    "100 EUR",
    "31. augusta 2026",
    "úplné splatenie syntetickej pôžičky",
    "Súhlasím",
  ];
  const expectedFields = [
    "payer_identification",
    "recipient_identification",
    "amount",
    "payment_date",
    "payment_purpose",
  ];
  const headers = { "x-api-key": apiKey, Accept: "application/json" };
  let run: Record<string, unknown> = {};
  for (const [index, turn] of turns.entries()) {
    if (index > 0) {
      await reloadSelectedCase(page, input.caseTitle);
      const priorReply = index <= 5 ? expectedFields[index - 1] : "Súhlas platí iba pre tento beh";
      await expect(page.locator(".assistant-message").filter({ hasText: priorReply }).last()).toBeVisible({
        timeout: 60_000,
      });
    }
    await submitTurn(page, input.caseTitle, turn);
    await expect
      .poll(
        async () => {
          const response = await request.get(
            `${apiBaseUrl}/v1/case-workflows/runs/latest?case_id=${encodeURIComponent(input.caseId)}&user_id=${encodeURIComponent(input.user.userId)}`,
            { headers },
          );
          if (!response.ok()) return {};
          const candidate = (await response.json()) as Record<string, unknown>;
          const pending = (candidate.pending_action ?? {}) as Record<string, unknown>;
          const expected =
            index < 5
              ? candidate.status === "waiting_for_user" && pending.field === expectedFields[index]
              : index === 5
                ? candidate.status === "waiting_for_user" && pending.type === "tool_consent"
                : candidate.status === "completed";
          return expected;
        },
        { timeout: index < 5 ? 180_000 : 360_000 },
      )
      .toBe(true);
    const currentResponse = await request.get(
      `${apiBaseUrl}/v1/case-workflows/runs/latest?case_id=${encodeURIComponent(input.caseId)}&user_id=${encodeURIComponent(input.user.userId)}`,
      { headers },
    );
    run = (await currentResponse.json()) as Record<string, unknown>;
    if (index === 5) {
      const consent = (run.pending_action ?? {}) as Record<string, unknown>;
      expect(consent.tool_name).toBe(input.expectedTool);
      expect(consent.consent_scope).toBe(input.expectedConsentScope);
      expect(consent.consent_text_version).toBe(input.expectedConsentTextVersion);
      await expect(page.locator(".assistant-message").filter({ hasText: /Súhlas platí iba pre tento beh/i }).last()).toBeVisible();
    }
  }

  const runResponse = await request.get(
    `${apiBaseUrl}/v1/case-workflows/runs/latest?case_id=${encodeURIComponent(input.caseId)}&user_id=${encodeURIComponent(input.user.userId)}`,
    { headers },
  );
  expect(runResponse.ok()).toBeTruthy();
  run = (await runResponse.json()) as Record<string, unknown>;
  expect(run.graph_version).toBe(3);
  expect(run.flow_version).toBe(4);
  const toolResult = (run.tool_results as Array<Record<string, unknown>>)[0]!;
  expect(toolResult.tool_name).toBe(input.expectedTool);
  expect(toolResult.status).toBe("succeeded");
  expect(toolResult.record_count).toBe(1);
  expect(toolResult.consent_text_version).toBe(input.expectedConsentTextVersion);
  expect(JSON.stringify(toolResult)).not.toContain("Testovacia");

  const eventsResponse = await request.get(
    `${apiBaseUrl}/v1/case-workflows/runs/${encodeURIComponent(String(run.workflow_run_id))}/events?user_id=${encodeURIComponent(input.user.userId)}`,
    { headers },
  );
  expect(eventsResponse.ok()).toBeTruthy();
  const events = ((await eventsResponse.json()) as { items: Array<Record<string, unknown>> }).items;
  const eventTypes = events.map((event) => String(event.event_type));
  for (const eventType of [
    "legal_requirements_retrieved",
    "tool_consent_recorded",
    "consented_tools_completed",
    "privacy_safety_validation_completed",
    "langgraph_run_completed",
  ]) expect(eventTypes).toContain(eventType);
  const retrievalEvent = events.find((event) => event.event_type === "legal_requirements_retrieved")!;
  const observedLegalSourceIds = String(
    (retrievalEvent.details as Record<string, unknown>).source_ids ?? "",
  ).split(",").filter(Boolean);
  expect(observedLegalSourceIds).toContain(input.expectedLegalSourceId);

  const ledger = await readLedger(String(run.workflow_run_id));
  expect(ledger.consentCount).toBe(1);
  expect(ledger.executionCount).toBe(1);
  expect(ledger.decision).toBe("granted");
  expect(ledger.scope).toBe(input.expectedConsentScope);
  expect(ledger.textVersion).toBe(input.expectedConsentTextVersion);
  expect(ledger.toolName).toBe(input.expectedTool);

  const artifact = (run.artifacts as Array<Record<string, unknown>>)[0]!;
  expect(artifact.provider).toBe(input.expectedProvider);
  expect(artifact.model).toBe(input.expectedModel);
  const pdfResponse = await request.get(
    `${apiBaseUrl}/v1/case-workflows/runs/${encodeURIComponent(String(run.workflow_run_id))}/artifacts/${encodeURIComponent(String(artifact.artifact_id))}/pdf?user_id=${encodeURIComponent(input.user.userId)}`,
    { headers },
  );
  expect(pdfResponse.ok()).toBeTruthy();
  const pdfPath = path.join(evidenceRoot, "payment-confirmation.pdf");
  const firstPagePath = path.join(evidenceRoot, "payment-confirmation-first-page.png");
  await writeFile(pdfPath, await pdfResponse.body());
  const pdf = await renderAndValidatePdf(pdfPath, firstPagePath);
  expect(pdf.pageCount).toBeGreaterThan(0);
  expect(pdf.extractedText).toContain("100 EUR");

  const finalMessage = page.locator(".assistant-message").filter({ hasText: input.expectedTool }).last();
  await expect(finalMessage).toBeVisible({ timeout: 60_000 });
  await expect(finalMessage).toContainText("succeeded");
  await expect(finalMessage).toContainText(/ľudskú kontrolu/i);
  await finalMessage.scrollIntoViewIfNeeded();
  const screenshotPath = path.join(evidenceRoot, "langgraph-consented-tool-final.png");
  await page.screenshot({ path: screenshotPath, fullPage: true });

  const result = {
    schemaVersion: 1,
    scenarioId: "issue-716-langgraph-consented-tools",
    runId: input.runId,
    syntheticOnly: true,
    services: ["frontend", "api", "mcp", "postgresql", "azure-foundry", "tool-registry"],
    provider: artifact.provider,
    model: artifact.model,
    workflowRunId: run.workflow_run_id,
    graph: `${run.graph_key}@${run.graph_version}`,
    flow: `${run.flow_key}@${run.flow_version}`,
    tool: toolResult,
    consent: ledger,
    observedEventIds: events.map((event) => event.event_id),
    expectedLegalSourceId: input.expectedLegalSourceId,
    observedLegalSourceIds,
    pdf: path.basename(pdfPath),
    firstPage: path.basename(firstPagePath),
    screenshot: path.basename(screenshotPath),
    retention: "Delete ignored evidence within 7 days.",
  };
  await writeFile(path.join(evidenceRoot, "result-manifest.json"), `${JSON.stringify(result, null, 2)}\n`);

  const cleanup = await request.delete(
    `${apiBaseUrl}/v1/cases/${encodeURIComponent(input.caseId)}?user_id=${encodeURIComponent(input.user.userId)}`,
    { headers },
  );
  expect(cleanup.status()).toBe(204);
  const removedLedger = await readLedger(String(run.workflow_run_id));
  expect(removedLedger.consentCount).toBe(0);
  expect(removedLedger.executionCount).toBe(0);
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
    const submitted = await streamResponse.then(
      (response) => response.ok(),
      () => false,
    );
    if (submitted) return;
    await reloadSelectedCase(page, caseTitle);
  }
  throw new Error(`Composer did not submit the reviewed turn: ${value}`);
}

async function readLedger(workflowRunId: string) {
  const python = process.env.PYTHON ?? path.resolve(process.cwd(), "../../conda/python.exe");
  const script = [
    "import json, os, psycopg, sys",
    "from dotenv import load_dotenv",
    "load_dotenv(os.path.abspath(os.path.join(os.getcwd(), '..', '..', '.env')))",
    "run_id = sys.argv[1]",
    "with psycopg.connect(os.environ['DB_CLOUD']) as conn:",
    "  with conn.cursor() as cur:",
    "    cur.execute('SELECT tool_name, consent_scope, consent_text_version, decision FROM workflow_tool_consent_events WHERE workflow_run_id=%s', (run_id,))",
    "    consent = cur.fetchone()",
    "    cur.execute('SELECT COUNT(*) FROM workflow_tool_execution_events WHERE workflow_run_id=%s', (run_id,))",
    "    executions = cur.fetchone()[0]",
    "print(json.dumps({'consentCount': 1 if consent else 0, 'executionCount': executions, 'toolName': consent[0] if consent else '', 'scope': consent[1] if consent else '', 'textVersion': consent[2] if consent else '', 'decision': consent[3] if consent else ''}))",
  ].join("\n");
  const { stdout } = await execFileAsync(python, ["-c", script, workflowRunId], { encoding: "utf8" });
  return JSON.parse(stdout.trim()) as {
    consentCount: number; executionCount: number; toolName: string;
    scope: string; textVersion: string; decision: string;
  };
}

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
    encoding: "utf8", env: { ...process.env, PYTHONIOENCODING: "utf-8" },
  });
  const jsonLine = stdout
    .trim()
    .split(/\r?\n/)
    .reverse()
    .find((line) => line.trimStart().startsWith("{"));
  if (!jsonLine) throw new Error("PDF validation did not emit a JSON result.");
  return JSON.parse(jsonLine) as { pageCount: number; extractedText: string };
}
