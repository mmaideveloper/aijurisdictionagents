import { expect, test, type APIRequestContext } from "@playwright/test";
import { createHash } from "node:crypto";
import fs from "node:fs";

type Decision = {
  decision_id: string;
  file_number: string;
  issue_date: string;
};

type Manifest = {
  schema_version: number;
  run_id: string;
  synthetic_only: boolean;
  question: string;
  user: { userId: string; email: string; name: string };
  case_id: string;
  case_title: string;
  provider: string;
  model: string;
  model_profile_id: string;
  model_parameters: Record<string, boolean | number | string | null>;
  expected_decisions: Decision[];
  status: string;
  [key: string]: unknown;
};

type Citation = {
  source_type?: string;
  source_id?: string;
  file_number?: string;
  decision_date?: string;
  retrieval_tool?: string;
};

const manifestPath = process.env.ISSUE_651_E2E_MANIFEST?.trim();
const screenshotPath = process.env.ISSUE_651_E2E_SCREENSHOT?.trim();
const apiBaseUrl = process.env.VITE_API_BASE_URL?.trim().replace(/\/$/, "") || "";
const mcpBaseUrl = process.env.ISSUE_651_MCP_BASE_URL?.trim().replace(/\/$/, "") || "";
const internalSecret = process.env.ISSUE_651_INTERNAL_MCP_SECRET?.trim() || "";
const apiKey = process.env.VITE_API_KEY?.trim() || "aijuris";
const hasLiveSetup = Boolean(
  manifestPath && screenshotPath && apiBaseUrl && mcpBaseUrl && internalSecret && fs.existsSync(manifestPath),
);

test.skip(!hasLiveSetup, "Run scripts/run_issue_651_latest_court_e2e.ps1 first.");
test.setTimeout(360_000);

test.afterEach(async ({ page }, testInfo) => {
  if (!screenshotPath || fs.existsSync(screenshotPath)) {
    return;
  }
  await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => undefined);
  if (manifestPath && fs.existsSync(manifestPath) && testInfo.status !== "passed") {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8")) as Manifest;
    manifest.status = "failed";
    manifest.failure_category = "real_e2e_assertion_failed";
    fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2), "utf-8");
  }
});

test("returns the true latest five metadata decisions through Azure gpt-5-mini", async ({ page, request }) => {
  const manifest = JSON.parse(fs.readFileSync(manifestPath!, "utf-8")) as Manifest;
  expect(manifest.synthetic_only).toBe(true);
  expect(manifest.model).toBe("gpt-5-mini");
  expect(manifest.expected_decisions).toHaveLength(5);

  const directPayload = await callCourtSearch(request, manifest.question);
  expect(directPayload.query_mode).toBe("latest_metadata");
  expect(directPayload.sort).toBe("latest");
  expect(directPayload.metadata_only).toBe(true);
  expect((directPayload.data_quality as Record<string, unknown>).topic_filter_applied).toBe(false);
  const directResults = directPayload.results as Array<Record<string, unknown>>;
  expect(directResults.map((item) => String(item.decision_id))).toEqual(
    manifest.expected_decisions.map((item) => item.decision_id),
  );
  expect(directResults.map((item) => String(item.issue_date))).toEqual(
    manifest.expected_decisions.map((item) => item.issue_date),
  );

  await page.addInitScript((user) => {
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
    window.localStorage.setItem("aj_frontend_lang", "sk");
  }, manifest.user);

  await page.setViewportSize({ width: 1440, height: 1200 });
  await page.goto("/app/assistant", { waitUntil: "domcontentloaded" });
  await page.getByText(manifest.case_title, { exact: true }).click();
  await expect(page.locator(".assistant-model-disclosure")).toContainText(manifest.provider);
  await expect(page.locator(".assistant-model-disclosure")).toContainText(manifest.model);
  await page.locator(".assistant-composer__input").fill(manifest.question);
  await page.locator(".assistant-composer__send").click();

  const history = await pollHistory(request, manifest);
  const assistantMessages = (history.messages as Array<Record<string, unknown>>).filter(
    (message) => message.role === "assistant",
  );
  const answer = String(assistantMessages.at(-1)?.content ?? "");
  expect(answer).not.toMatch(/MCP lookup.*nedostup|nemam priamy pristup/i);
  const citations = (history.citations as Citation[]).filter(
    (citation) => citation.source_type === "court_decision",
  );
  expect(citations).toHaveLength(5);
  expect(citations.map((citation) => citation.source_id)).toEqual(
    manifest.expected_decisions.map((item) => item.decision_id),
  );
  expect(citations.map((citation) => citation.decision_date)).toEqual(
    manifest.expected_decisions.map((item) => item.issue_date),
  );
  expect(citations.every((citation) => /JurisDigta MCP/.test(citation.retrieval_tool ?? ""))).toBe(true);
  await expect(page.locator(".assistant-tool-panel")).toContainText(/JurisDigta MCP/i);
  await expect(page.locator(".assistant-thread__viewport .citation-list__item")).toHaveCount(5);

  const routeResponse = await request.get(
    `${apiBaseUrl}/v1/model-routing/effective?task_type=chat_reply&user_id=${encodeURIComponent(manifest.user.userId)}`,
    { headers: { "x-api-key": apiKey } },
  );
  expect(routeResponse.ok()).toBe(true);
  const route = (await routeResponse.json()) as Record<string, unknown>;
  expect(String(route.provider)).toMatch(/azure.?foundry/i);
  expect(route.model).toBe("gpt-5-mini");
  expect(String(route.route_type)).not.toMatch(/fallback/i);

  await page.screenshot({ path: screenshotPath!, fullPage: true });
  manifest.status = "passed";
  manifest.actual_route = {
    provider: route.provider,
    model: route.model,
    model_profile_id: route.model_profile_id,
    route_type: route.route_type,
  };
  manifest.observed_decision_ids = citations.map((citation) => citation.source_id);
  manifest.answer_sha256 = createHash("sha256").update(answer).digest("hex");
  fs.writeFileSync(manifestPath!, JSON.stringify(manifest, null, 2), "utf-8");
});

async function callCourtSearch(
  request: APIRequestContext,
  query: string,
): Promise<Record<string, unknown>> {
  const response = await request.post(`${mcpBaseUrl}/mcp`, {
    headers: {
      "content-type": "application/json",
      "x-jurisdigta-internal-mcp-secret": internalSecret,
    },
    data: {
      jsonrpc: "2.0",
      id: "issue-651-direct",
      method: "tools/call",
      params: { name: "searchCourtDecisions", arguments: { query, limit: 5, sort: "latest" } },
    },
  });
  expect(response.ok()).toBe(true);
  const envelope = (await response.json()) as Record<string, unknown>;
  const result = envelope.result as { content?: Array<{ text?: string }> };
  expect(result.content?.[0]?.text).toBeTruthy();
  return JSON.parse(result.content![0].text!) as Record<string, unknown>;
}

async function pollHistory(
  request: APIRequestContext,
  manifest: Manifest,
): Promise<Record<string, unknown>> {
  const url =
    `${apiBaseUrl}/v1/cases/${encodeURIComponent(manifest.case_id)}/history` +
    `?user_id=${encodeURIComponent(manifest.user.userId)}&limit=20`;
  const deadline = Date.now() + 300_000;
  while (Date.now() < deadline) {
    const response = await request.get(url, { headers: { "x-api-key": apiKey } });
    expect(response.ok()).toBe(true);
    const history = (await response.json()) as Record<string, unknown>;
    const messages = (history.messages ?? []) as Array<Record<string, unknown>>;
    const courtCitations = ((history.citations ?? []) as Citation[]).filter(
      (citation) => citation.source_type === "court_decision",
    );
    if (messages.some((message) => message.role === "assistant") && courtCitations.length === 5) {
      return history;
    }
    await new Promise((resolve) => setTimeout(resolve, 1_000));
  }
  throw new Error("Timed out waiting for the synthetic assistant response.");
}
