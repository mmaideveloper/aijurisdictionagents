import { expect, test } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const manifestPath = process.env.ISSUE_721_E2E_MANIFEST?.trim() ?? "";
const evidenceRoot = process.env.ISSUE_721_E2E_EVIDENCE?.trim() ?? "";
const apiBaseUrl = (process.env.ISSUE_721_API_BASE_URL ?? "http://127.0.0.1:8080").replace(/\/$/, "");
const apiKey = process.env.ISSUE_721_API_KEY ?? "aijuris";

type Manifest = {
  syntheticOnly: true;
  runId: string;
  question: string;
  expectedDocumentId: string;
  expectedLawIdentifier: string;
  expectedAmendmentCount: number;
  expectedProvider: string;
  expectedModel: string;
  caseId: string;
  caseTitle: string;
  user: { userId: string; email: string; name: string };
};

test.skip(!manifestPath || !evidenceRoot, "Prepare issue #721 local PostgreSQL E2E evidence first.");
test.setTimeout(720_000);

test("real local UI returns the MCP-ranked most-amended synthetic 2025 law", async ({ page, request }) => {
  const input = JSON.parse(await readFile(manifestPath, "utf8")) as Manifest;
  expect(input.syntheticOnly).toBe(true);
  await mkdir(evidenceRoot, { recursive: true });
  await page.addInitScript((user) => {
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
    window.localStorage.setItem("aj_frontend_lang", "en");
  }, input.user);
  await page.goto("/app/assistant", { waitUntil: "domcontentloaded" });
  await page.getByText(input.caseTitle, { exact: true }).click({ timeout: 60_000 });
  await page.locator(".assistant-composer__input").fill(input.question);
  await page.locator(".assistant-composer__send").click();
  const answer = page.locator(".assistant-message").last();
  await expect(answer).toContainText(input.expectedLawIdentifier, { timeout: 660_000 });
  await expect(answer).toContainText(`${input.expectedAmendmentCount} distinct recorded amending acts`);
  await expect(answer).toContainText("does not prove that a law is incorrect");
  await expect(answer).toContainText("human review is required");

  const headers = { "x-api-key": apiKey, Accept: "application/json" };
  const historyResponse = await request.get(
    `${apiBaseUrl}/v1/cases/${encodeURIComponent(input.caseId)}/history?user_id=${encodeURIComponent(input.user.userId)}&limit=20`,
    { headers },
  );
  expect(historyResponse.ok()).toBeTruthy();
  const history = (await historyResponse.json()) as {
    citations?: Array<{ source_id?: string; retrieval_tool?: string }>;
  };
  const citation = (history.citations ?? []).find((item) => item.source_id === input.expectedDocumentId);
  expect(citation).toBeTruthy();
  expect(citation?.retrieval_tool).toContain("rankLawsByAmendments");

  const screenshot = path.join(evidenceRoot, "issue-721-law-analytics-final.png");
  await answer.scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot, fullPage: true });
  await writeFile(
    path.join(evidenceRoot, "result-manifest.json"),
    `${JSON.stringify({
      schemaVersion: 1,
      scenarioId: "issue-721-law-analytics",
      runId: input.runId,
      syntheticOnly: true,
      services: ["frontend", "api", "mcp", "postgresql", "configured-real-model"],
      provider: input.expectedProvider,
      model: input.expectedModel,
      metric: "distinct_amending_acts",
      expectedSourceId: input.expectedDocumentId,
      observedSourceId: citation?.source_id,
      screenshot: path.basename(screenshot),
      retention: "Delete ignored evidence within 7 days.",
    }, null, 2)}\n`,
  );
  const cleanup = await request.delete(
    `${apiBaseUrl}/v1/cases/${encodeURIComponent(input.caseId)}?user_id=${encodeURIComponent(input.user.userId)}`,
    { headers },
  );
  expect(cleanup.status()).toBe(204);
});
