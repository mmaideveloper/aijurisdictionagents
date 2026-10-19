import { test, expect, type Browser } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const output = path.resolve("../../runs/issue922");
const api = "http://127.0.0.1:8922";
const auth = (role: string) => JSON.parse(fs.readFileSync(path.join(output, `private-${role}.json`), "utf8"));
const headers = (user: ReturnType<typeof auth>) => ({ "x-api-key": "aijuris", "x-jurisdigta-user-id": user.userId, "x-jurisdigta-device-id": user.deviceId, "x-jurisdigta-device-token": user.deviceAuthToken });

async function session(browser: Browser, user: ReturnType<typeof auth>) {
  const context = await browser.newContext({ viewport: { width: 1600, height: 1100 } });
  await context.addInitScript(value => {
    sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(value));
    localStorage.setItem("aj_frontend_lang", "sk");
  }, user);
  return { context, page: await context.newPage() };
}

test("encrypted case read by real AI and exported only after owner consent", async ({ browser, request }) => {
  const manifest = JSON.parse(fs.readFileSync(path.join(output, "input-manifest.json"), "utf8"));
  const owner = auth("owner"), admin = auth("admin"), other = auth("other");
  const ownerSession = await session(browser, owner);
  const page = ownerSession.page;
  page.on("response", async response => {
    if (response.url().endsWith("/stream") && response.request().method() === "POST") {
      try { fs.writeFileSync(path.join(output, "synthetic-stream.txt"), await response.text()); } catch { /* aborted response */ }
    }
  });
  await page.goto("http://127.0.0.1:5192/app/case");
  await page.getByLabel("Názov prípadu", { exact: true }).fill(manifest.runId);
  await page.getByLabel("Jurisdikcia", { exact: true }).fill("Slovensko");
  await page.getByLabel("Protistrana", { exact: true }).fill("Synteticka protistrana");
  const created = page.waitForResponse(r => r.url().endsWith("/v1/cases") && r.request().method() === "POST");
  await page.locator("form button[type=submit]").click();
  const createdResponse = await created;
  expect(createdResponse.status()).toBe(201);
  const record = await createdResponse.json();
  fs.writeFileSync(path.join(output, "case-id.json"), JSON.stringify({ caseId: record.case_id }));
  const uploaded = await request.post(`${api}/v1/cases/${record.case_id}/documents?user_id=${owner.userId}`, {
    headers: headers(owner), multipart: { files: { name: "synthetic-source.pdf", mimeType: "application/pdf", buffer: fs.readFileSync(path.join(output, "synthetic-source.pdf")) } }, timeout: 120000,
  });
  expect(uploaded.ok()).toBeTruthy();
  const uploadResult = await uploaded.json();
  expect(uploadResult.processed_document_count).toBeGreaterThan(0);
  const leaked = await request.get(`${api}/v1/cases/${record.case_id}/history?user_id=${owner.userId}`, { headers: headers(other) });
  expect(leaked.status()).toBe(401);
  const unauthenticated = await request.get(`${api}/v1/cases/${record.case_id}/history?user_id=${owner.userId}`, { headers: { "x-api-key": "aijuris" } });
  expect(unauthenticated.status()).toBe(401);
  const directExport = await request.get(`${api}/v1/admin/cases/${record.case_id}/export?user_id=${owner.userId}&reason=synthetic`, { headers: { ...headers(admin), "x-jurisdigta-admin-user-id": admin.userId } });
  expect(directExport.status()).toBe(403);
  const hydrated = page.waitForResponse(r => r.url().includes(`/v1/cases/${record.case_id}/history`) && r.status() === 200);
  await page.goto(`http://127.0.0.1:5192/case/${record.case_id}`);
  await hydrated;
  await expect(page.getByText("synthetic-source.pdf", { exact: true }).first()).toBeVisible();
  await expect(page.locator(".assistant-composer__input")).toBeVisible();
  await page.locator(".assistant-composer__input").fill("Precitaj prilozeny dokument. Aka je presna suma pozicky a kontrolny identifikator? Uved zdroj dokumentu. Nevytvaraj novy dokument.");
  const streamFinished = page.waitForResponse(r => r.url().endsWith("/stream") && r.request().method() === "POST").then(r => r.finished());
  await page.locator(".assistant-composer__send").click();
  const thread = page.locator(".assistant-thread__viewport");
  await expect(thread).toContainText("BLUE-922", { timeout: 180000 });
  await expect(thread).toContainText(/7[\s,.]?319/, { timeout: 180000 });
  await streamFinished;
  await page.screenshot({ path: path.join(output, "encrypted-case-answer.png") });

  const adminSession = await session(browser, admin);
  await adminSession.page.goto("http://127.0.0.1:5192/app/admin");
  await adminSession.page.screenshot({ path: path.join(output, "admin-before-request.png") });
  await adminSession.page.locator(".admin-sidebar__item").filter({ hasText: /prípad|case/i }).first().click();
  await adminSession.page.screenshot({ path: path.join(output, "admin-request-panel.png") });
  const panel = adminSession.page.getByRole("region", { name: "Case export consent" });
  await panel.getByLabel("Selected case IDs").fill(record.case_id);
  await panel.getByLabel("Purpose", { exact: true }).fill("Synthetic encrypted export acceptance");
  const requested = adminSession.page.waitForResponse(r => r.url().endsWith("/v1/case-exports") && r.request().method() === "POST");
  await panel.getByRole("button", { name: "Request owner consent" }).click();
  const response = await requested;
  expect(response.status()).toBe(202);
  const exportId = (await response.json()).request_id;
  const premature = await request.post(`${api}/v1/case-exports/${exportId}/download`, { headers: headers(admin) });
  expect(premature.status()).toBe(403);
  const forged = await request.post(`${api}/v1/case-exports/${exportId}/decision`, { headers: headers(other), data: { decision: "approved" } });
  expect(forged.status()).toBe(403);
  await page.goto("http://127.0.0.1:5192/app/profile");
  const consent = page.getByTestId("case-export-request").filter({ hasText: exportId });
  await expect(consent).toContainText(admin.userId);
  await consent.getByRole("button", { name: "Approve this export" }).click();
  await expect(consent).toContainText("approved");
  await expect(panel.getByTestId("case-export-request").filter({ hasText: exportId })).toContainText("ready", { timeout: 90000 });
  const downloadPromise = adminSession.page.waitForEvent("download");
  await panel.getByTestId("case-export-request").filter({ hasText: exportId }).getByRole("button", { name: "Download once" }).click();
  await (await downloadPromise).saveAs(path.join(output, "consented-export.zip"));
  expect((await request.post(`${api}/v1/case-exports/${exportId}/download`, { headers: headers(admin) })).status()).toBe(403);
  await page.getByRole("button", { name: "Refresh export requests" }).click();
  await expect(consent).toContainText("downloaded");
  await page.screenshot({ path: path.join(output, "owner-export-completed.png") });
  const history = await (await request.get(`${api}/v1/cases/${record.case_id}/history?user_id=${owner.userId}`, { headers: headers(owner) })).json();
  const audit = await (await request.get(`${api}/v1/cases/${record.case_id}/ai-model-audit?user_id=${owner.userId}`, { headers: headers(owner) })).json();
  const routes = audit.entries.map((item: { provider: string; model: string; status: string }) => ({ provider: item.provider, model: item.model, status: item.status }));
  expect(routes.some((r: { provider: string; model: string }) => r.provider === "azure_foundry" && r.model === "gpt-4o-mini")).toBeTruthy();
  fs.writeFileSync(path.join(output, "browser-result.json"), JSON.stringify({ runId: manifest.runId, caseId: record.case_id, exportId, routes,
    observedSourceIds: (history.citations ?? []).map((c: { source_id: string }) => c.source_id), expectedDocumentId: uploadResult.uploaded[0].doc_id,
    services: ["frontend:5192", "api:8922", "mcp:8923", "postgres:5432/issue922", "postgres:5433/issue922_e2e_laws"],
    ownerConsent: true, forgedConsentDenied: true, crossUserDenied: true, replayDenied: true, archiveValidation: "pending", syntheticOnly: true,
    retention: "Delete evidence within seven days; delete private authentication files immediately after acceptance." }, null, 2));
  await ownerSession.context.close(); await adminSession.context.close();
});
