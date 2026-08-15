import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { expect, test, type Route } from "@playwright/test";

const adminUser = {
  userId: "issue-621-admin",
  deviceId: "issue-621-device",
  deviceAuthToken: "synthetic-device-token",
  email: "issue-621-admin@example.test",
  name: "Issue 621 Admin",
  role: "admin",
  isEnabled: true
};

const provider = {
  provider_id: "azure_foundry_eu",
  provider_code: "azure_foundry_eu",
  provider_type: "azurefoundry",
  display_name: "azureFoundryEU",
  base_url: "https://synthetic.example.test/api/projects/legal",
  api_version: "preview",
  region: "westeurope",
  data_zone: "eu",
  is_external: true,
  is_local: false,
  health_check_url: "",
  model_parameters: { temperature: 0.2 },
  enabled: true,
  created_at: "2026-08-15T12:00:00Z",
  updated_at: "2026-08-15T12:00:00Z",
  deleted_at: null,
  deleted_by_admin_user_id: "",
  deleted_reason: ""
};

const profile = {
  model_profile_id: "azure_foundry_eu_gpt_5_mini",
  provider_id: provider.provider_id,
  model_code: "gpt-5-mini",
  deployment_name: "gpt-5-mini",
  model_parameters: { temperature: null, max_completion_tokens: 512 },
  context_window_tokens: 128000,
  input_price_per_1m: 0,
  cached_input_price_per_1m: 0,
  output_price_per_1m: 0,
  billing_currency: "EUR",
  effective_from: null,
  effective_to: null,
  eu_data_zone_capable: true,
  is_default_for_free: false,
  enabled: true,
  created_at: "2026-08-15T12:00:00Z",
  updated_at: "2026-08-15T12:00:00Z",
  deleted_at: null,
  deleted_by_admin_user_id: "",
  deleted_reason: ""
};

const dashboard = {
  providers: [provider],
  profiles: [profile],
  credentials: [],
  policies: [],
  groups: [],
  memberships: [],
  users: [],
  users_page: { total: 0, limit: 25, offset: 0 },
  audit_events: [],
  route_priority: [],
  compliance_notes: [],
  grafana_url: ""
};

const fulfillJson = (route: Route, body: unknown) =>
  route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });

test("admin saves a gpt-5-mini profile that removes inherited temperature", async ({ page }, testInfo) => {
  let savedBody: Record<string, unknown> | null = null;
  await page.route("**/v1/admin/ai-models", (route) => fulfillJson(route, dashboard));
  await page.route("**/v1/admin/users?**", (route) =>
    fulfillJson(route, { users: [], total: 0, limit: 25, offset: 0 })
  );
  await page.route("**/v1/admin/ai-models/ollama/models", (route) =>
    fulfillJson(route, { base_url: "http://127.0.0.1:11434", models: [] })
  );
  await page.route("**/v1/admin/ai-models/profiles", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    savedBody = route.request().postDataJSON() as Record<string, unknown>;
    await fulfillJson(route, { ...profile, ...savedBody, updated_at: "2026-08-15T12:05:00Z" });
  });

  await page.addInitScript((user) => {
    window.localStorage.setItem("aj_frontend_lang", "en");
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
  }, adminUser);
  await page.setViewportSize({ width: 1600, height: 1050 });
  await page.goto("/app/admin", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Models and prices" }).click();
  await page.getByRole("button", { name: "Edit" }).click();

  const parameters = page.getByLabel("adminProfileModelParameters");
  await expect(parameters).toHaveValue(/"temperature": null/);
  await expect(parameters).toHaveValue(/"max_completion_tokens": 512/);
  await page.getByLabel("Reason").fill("Configure gpt-5-mini supported request parameters.");
  await page.getByRole("button", { name: "Save model" }).click();

  await expect(page.getByText("Model profile was saved and the table was refreshed.")).toBeVisible();
  expect(savedBody).toMatchObject({
    model_profile_id: profile.model_profile_id,
    model_parameters: { temperature: null, max_completion_tokens: 512 }
  });
  await expect(page.getByText("max_completion_tokens, temperature")).toBeVisible();

  const screenshotPath = path.resolve(
    process.cwd(),
    "../../docs/screenshots/issue-621/issue-621-model-parameters-admin.png"
  );
  const evidenceDirectory = path.resolve(process.cwd(), "../../runs/e2e/issue-621");
  await mkdir(path.dirname(screenshotPath), { recursive: true });
  await mkdir(evidenceDirectory, { recursive: true });
  await page.screenshot({ path: screenshotPath, fullPage: true });
  await testInfo.attach("issue-621-model-parameters-admin.png", {
    path: screenshotPath,
    contentType: "image/png"
  });
  await writeFile(
    path.join(evidenceDirectory, "result.json"),
    `${JSON.stringify({
      issue: 621,
      scenario: "gpt-5-mini-profile-unsets-provider-temperature",
      syntheticDataOnly: true,
      liveAzureExecuted: false,
      profileParameters: profile.model_parameters,
      screenshot: path.basename(screenshotPath)
    }, null, 2)}\n`,
    "utf8"
  );
});
