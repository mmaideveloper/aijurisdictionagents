import { expect, test } from "@playwright/test";
import { execFile } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const apiBaseUrl = (process.env.ISSUE_635_API_BASE_URL ?? "http://127.0.0.1:8080").replace(/\/$/, "");
const apiKey = process.env.ISSUE_635_API_KEY ?? "aijuris";
const manifestInput = process.env.ISSUE_635_E2E_MANIFEST?.trim() ?? "";
const evidenceRoot = process.env.ISSUE_635_E2E_EVIDENCE?.trim() ?? "";
const enabled = Boolean(manifestInput && evidenceRoot);

type InputManifest = {
  syntheticOnly: true;
  runId: string;
  user: { userId: string; email: string; name: string };
  caseId: string;
  caseTitle: string;
  expectedProvider: string;
  expectedModel: string;
};

test.skip(!enabled, "Prepare real local services and set ISSUE_635_E2E_MANIFEST/EVIDENCE.");
test.setTimeout(720_000);

test("real local frontend executes persisted LangGraph interrupt/resume and reviewed PDF", async ({ page, request }) => {
  const input = JSON.parse(await readFile(manifestInput, "utf8")) as InputManifest;
  expect(input.syntheticOnly).toBe(true);
  await mkdir(evidenceRoot, { recursive: true });
  await page.addInitScript((user) => {
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
    window.localStorage.setItem("aj_frontend_lang", "sk");
  }, input.user);

  await page.goto("/app/assistant", { waitUntil: "domcontentloaded" });
  await page.getByText(input.caseTitle, { exact: true }).click({ timeout: 60_000 });
  const composer = page.locator(".assistant-composer__input");
  const send = page.locator(".assistant-composer__send");
  const headers = { "x-api-key": apiKey, Accept: "application/json" };
  const turns = [
    "Priprav mi potvrdenie o zaplatení pôžičky.",
    "Syntetický Platiteľ A",
    "Syntetický Príjemca B",
    "100 EUR",
    "26. augusta 2026",
    "úplné splatenie syntetickej pôžičky",
  ];
  const expectedPendingFields = [
    "payer_identification",
    "recipient_identification",
    "amount",
    "payment_date",
    "payment_purpose",
  ];
  for (const [index, turn] of turns.entries()) {
    if (index > 0) {
      await reloadSelectedCase(page, input.caseTitle);
      await expect(
        page
          .locator(".assistant-message")
          .filter({ hasText: new RegExp(expectedPendingFields[index - 1], "i") })
          .last(),
      ).toBeVisible({ timeout: 60_000 });
    }
    let ready = false;
    for (let attempt = 0; attempt < 3 && !ready; attempt += 1) {
      await expect(composer).toBeEnabled({ timeout: 60_000 });
      await composer.fill(turn);
      ready = await send.isEnabled();
      if (!ready) {
        await expect(send).toBeEnabled({ timeout: 10_000 }).then(
          () => {
            ready = true;
          },
          () => undefined,
        );
      }
      if (!ready) await reloadSelectedCase(page, input.caseTitle);
    }
    expect(ready, `Composer did not hydrate for turn ${index + 1}`).toBe(true);
    await send.click();
    const expectedState =
      index < turns.length - 1
        ? `waiting_for_user:${expectedPendingFields[index]}`
        : "completed:";
    await expect
      .poll(
        async () => {
          const response = await request.get(
            `${apiBaseUrl}/v1/case-workflows/runs/latest?case_id=${encodeURIComponent(input.caseId)}&user_id=${encodeURIComponent(input.user.userId)}`,
            { headers },
          );
          if (!response.ok()) return `http-${response.status()}`;
          const run = (await response.json()) as Record<string, unknown>;
          const pending = (run.pending_action ?? {}) as Record<string, unknown>;
          return `${String(run.status)}:${String(pending.field ?? "")}`;
        },
        { timeout: index < turns.length - 1 ? 180_000 : 360_000 },
      )
      .toBe(expectedState);
    const expectedReply =
      index < turns.length - 1
        ? /Workflow LangGraph potrebuje doplniť/i
        : /ľudskú kontrolu/i;
    const response = page.locator(".assistant-message").filter({ hasText: expectedReply }).last();
    await expect(response).toBeVisible({ timeout: 60_000 });
    if (index < turns.length - 1) {
      await expect(response).toBeVisible({ timeout: 60_000 });
    } else {
      await expect(response).toBeVisible({ timeout: 60_000 });
      await expect(response).toContainText(/100 EUR/i);
    }
    const expectedMessageCount = (index + 1) * 2;
    await expect(
      page.locator("button").filter({ hasText: input.caseTitle }).first(),
    ).toContainText(`${expectedMessageCount} messages`, { timeout: 60_000 });
  }

  const runResponse = await request.get(
    `${apiBaseUrl}/v1/case-workflows/runs/latest?case_id=${encodeURIComponent(input.caseId)}&user_id=${encodeURIComponent(input.user.userId)}`,
    { headers },
  );
  expect(runResponse.ok()).toBeTruthy();
  const run = (await runResponse.json()) as Record<string, unknown>;
  expect(run.status).toBe("completed");
  expect(run.graph_key).toBe("legal_document_workflow");
  expect(run.graph_version).toBe(2);
  expect(run.flow_key).toBe("sk.civil.payment_confirmation");
  expect(run.flow_version).toBe(3);
  const eventsResponse = await request.get(
    `${apiBaseUrl}/v1/case-workflows/runs/${encodeURIComponent(String(run.workflow_run_id))}/events?user_id=${encodeURIComponent(input.user.userId)}`,
    { headers },
  );
  expect(eventsResponse.ok()).toBeTruthy();
  const events = ((await eventsResponse.json()) as { items: Array<Record<string, unknown>> }).items;
  const eventTypes = events.map((event) => String(event.event_type));
  const expectedEvents = [
    "langgraph_run_started",
    "workflow_routed",
    "workflow_assignment_pinned",
    "input_validation_completed",
    "workflow_interrupted",
    "workflow_resumed",
    "legal_requirements_retrieved",
    "output_validation_completed",
    "case_review_completed",
    "langgraph_run_completed",
  ];
  for (const eventType of expectedEvents) expect(eventTypes).toContain(eventType);
  for (let index = 1; index < expectedEvents.length; index += 1) {
    expect(eventTypes.indexOf(expectedEvents[index]!)).toBeGreaterThan(eventTypes.indexOf(expectedEvents[index - 1]!));
  }
  const retrievalEvent = events.find((event) => event.event_type === "legal_requirements_retrieved")!;
  expect((retrievalEvent.details as Record<string, unknown>).retrieval_policy_id).toBe(
    "sk.civil.payment_confirmation.legal_requirements.v1",
  );

  const artifact = (run.artifacts as Array<Record<string, unknown>>)[0]!;
  expect(String(artifact.provider)).toBe(input.expectedProvider);
  expect(String(artifact.model)).toBe(input.expectedModel);
  const pdfResponse = await request.get(
    `${apiBaseUrl}/v1/case-workflows/runs/${encodeURIComponent(String(run.workflow_run_id))}/artifacts/${encodeURIComponent(String(artifact.artifact_id))}/pdf?user_id=${encodeURIComponent(input.user.userId)}`,
    { headers },
  );
  expect(pdfResponse.ok()).toBeTruthy();
  const pdfPath = path.join(evidenceRoot, "payment-confirmation.pdf");
  const firstPagePath = path.join(evidenceRoot, "payment-confirmation-first-page.png");
  await writeFile(pdfPath, await pdfResponse.body());
  const pdfValidation = await renderAndValidatePdf(pdfPath, firstPagePath);
  expect(pdfValidation.pageCount).toBeGreaterThan(0);
  expect(pdfValidation.extractedText).toContain("100 EUR");
  expect(pdfValidation.extractedText).toContain("ľudskú kontrolu");

  const screenshotPath = path.join(evidenceRoot, "langgraph-final-state.png");
  await page
    .locator(".assistant-message")
    .filter({ hasText: /ľudskú kontrolu/i })
    .last()
    .scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshotPath, fullPage: true });
  const result = {
    schemaVersion: 1,
    scenarioId: "issue-635-langgraph-payment-confirmation",
    runId: input.runId,
    syntheticOnly: true,
    services: ["frontend", "api", "mcp", "postgresql", "azure-foundry"],
    provider: artifact.provider,
    model: artifact.model,
    workflowRunId: run.workflow_run_id,
    graph: `${run.graph_key}@${run.graph_version}`,
    flow: `${run.flow_key}@${run.flow_version}`,
    expectedEvents,
    observedEventIds: events.map((event) => event.event_id),
    legalSourceIds: events
      .filter((event) => event.event_type === "legal_requirements_retrieved")
      .map((event) => (event.details as Record<string, unknown>).source_ids),
    artifactId: artifact.artifact_id,
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
  const removedRun = await request.get(
    `${apiBaseUrl}/v1/case-workflows/runs/latest?case_id=${encodeURIComponent(input.caseId)}&user_id=${encodeURIComponent(input.user.userId)}`,
    { headers },
  );
  expect(removedRun.status()).toBe(404);
});

async function reloadSelectedCase(page: import("@playwright/test").Page, caseTitle: string) {
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByText(caseTitle, { exact: true }).click({ timeout: 60_000 });
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
