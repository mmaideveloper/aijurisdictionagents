import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const adminUser = {
  userId: "admin-1",
  deviceId: "web-device-1",
  deviceAuthToken: "device-token-1",
  email: "admin@example.test",
  name: "Admin User",
  role: "admin",
  isEnabled: true
};

test.use({ video: "on" });

const dashboard = {
  admin: { user_id: "admin-1", email: "admin@example.test" },
  providers: [
    {
      provider_id: "local_ollama",
      provider_code: "local_ollama",
      provider_type: "ollama",
      display_name: "Local Ollama",
      base_url: "http://127.0.0.1:11434/v1",
      api_version: "",
      region: "",
      data_zone: "local",
      is_external: false,
      is_local: true,
      health_check_url: "http://127.0.0.1:11434/api/tags",
      enabled: true,
      created_at: "2026-06-27T10:00:00Z",
      updated_at: "2026-06-27T10:00:00Z",
      deleted_at: null,
      deleted_by_admin_user_id: "",
      deleted_reason: ""
    },
    {
      provider_id: "azure_foundry",
      provider_code: "azure_foundry",
      provider_type: "azurefoundry",
      display_name: "Azure AI Foundry",
      base_url: "",
      api_version: "2024-10-21",
      region: "",
      data_zone: "eu",
      is_external: true,
      is_local: false,
      health_check_url: "",
      enabled: true,
      created_at: "2026-06-27T10:00:00Z",
      updated_at: "2026-06-27T10:00:00Z",
      deleted_at: null,
      deleted_by_admin_user_id: "",
      deleted_reason: ""
    }
  ],
  profiles: [
    {
      model_profile_id: "local_ollama_default",
      provider_id: "local_ollama",
      model_code: "qwen3:1.7b",
      deployment_name: "qwen3:1.7b",
      context_window_tokens: 0,
      input_price_per_1m: 0,
      cached_input_price_per_1m: 0,
      output_price_per_1m: 0,
      billing_currency: "EUR",
      effective_from: null,
      effective_to: null,
      eu_data_zone_capable: true,
      is_default_for_free: true,
      enabled: true,
      created_at: "2026-06-27T10:00:00Z",
      updated_at: "2026-06-27T10:00:00Z"
    },
    {
      model_profile_id: "azure_foundry_gpt_4o_mini",
      provider_id: "azure_foundry",
      model_code: "gpt-4o-mini",
      deployment_name: "gpt-4o-mini",
      context_window_tokens: 128000,
      input_price_per_1m: 0.15,
      cached_input_price_per_1m: 0.075,
      output_price_per_1m: 0.6,
      billing_currency: "USD",
      effective_from: null,
      effective_to: null,
      eu_data_zone_capable: true,
      is_default_for_free: false,
      enabled: true,
      created_at: "2026-06-27T10:00:00Z",
      updated_at: "2026-06-27T10:00:00Z"
    }
  ],
  credentials: [
    {
      credential_id: "azure_foundry:api_key:default",
      provider_id: "azure_foundry",
      credential_name: "default",
      secret_type: "api_key",
      secret_preview: "****cret",
      secret_value: null,
      enabled: true,
      created_at: "2026-06-27T10:00:00Z",
      updated_at: "2026-06-27T10:00:00Z",
      last_revealed_at: null
    }
  ],
  policies: [
    {
      policy_id: "default:free:default",
      task_type: "chat_reply",
      plan_code: "free",
      model_group_id: null,
      preferred_external_model_profile_id: null,
      preferred_local_model_profile_id: "local_ollama_default",
      allow_external: false,
      require_external_ack: true,
      require_eu_data_zone: true,
      fallback_local_on_error: true,
      fallback_local_on_budget: true,
      max_cost_eur: 0,
      priority: 0,
      enabled: true,
      created_at: "2026-06-27T10:00:00Z",
      updated_at: "2026-06-27T10:00:00Z"
    }
  ],
  groups: [
    {
      model_group_id: "admins",
      group_code: "admins",
      display_name: "Admins",
      priority: 100,
      enabled: true,
      created_at: "2026-06-27T10:00:00Z",
      updated_at: "2026-06-27T10:00:00Z"
    }
  ],
  memberships: [
    {
      model_group_id: "admins",
      user_id: "admin-1",
      email: "admin@example.test",
      full_name: "Admin User",
      created_at: "2026-06-27T10:00:00Z"
    }
  ],
  users: [
    {
      user_id: "admin-1",
      phone_number: null,
      email: "admin@example.test",
      full_name: "Admin User",
      role: "admin",
      is_enabled: true,
      created_at: "2026-06-27T10:00:00Z"
    }
  ],
  users_page: { total: 1, limit: 25, offset: 0 },
  audit_events: [
    {
      audit_event_id: "audit-1",
      admin_user_id: "admin-1",
      admin_email: "admin@example.test",
      action: "upsert",
      entity_type: "ai_task_route_policy",
      entity_id: "default:free:default",
      old_value_summary: "{}",
      new_value_summary: "{}",
      reason: "E2E route setup.",
      correlation_id: "corr-1",
      created_at: "2026-06-27T10:00:00Z"
    }
  ],
  route_priority: [],
  compliance_notes: [],
  grafana_url: "https://admin.jurisdigta.eu/grafana/"
};

test("admin management shows users, providers, models, policies, Ollama inventory, and audit records", async ({ page }) => {
  let adminHeader: string | null = null;
  let deviceHeader: string | null = null;

  await page.route("**/v1/admin/ai-models", async (route) => {
    adminHeader = route.request().headers()["x-jurisdigta-admin-user-id"] ?? null;
    deviceHeader = route.request().headers()["x-jurisdigta-device-token"] ?? null;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(dashboard) });
  });

  await page.route("**/v1/admin/ai-models/ollama/models", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        base_url: "http://127.0.0.1:11434",
        models: [
          {
            name: "qwen3:1.7b",
            model: "qwen3:1.7b",
            modified_at: "2026-06-27T10:00:00Z",
            size: 1700000000,
            digest: "sha256:qwen",
            details: {},
            installed: true,
            configured_profile_ids: ["local_ollama_default"],
            active_policy_ids: ["default:free:default"],
            is_default: true,
            is_running: false,
            removable: false,
            removal_blockers: ["Profile local_ollama_default is the seeded system local default."]
          }
        ]
      })
    });
  });

  await page.addInitScript((user) => {
    window.localStorage.setItem("aj_frontend_lang", "en");
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
  }, adminUser);

  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto("/app/admin", { waitUntil: "domcontentloaded" });

  await expect(page.getByText("Admin User (admin@example.test)")).toBeVisible();
  await expect(page.getByText("1-1 of 1")).toBeVisible();
  expect(adminHeader).toBe("admin-1");
  expect(deviceHeader).toBe("device-token-1");

  await page.getByRole("button", { name: "Providers" }).click();
  await expect(page.getByRole("cell", { name: "Local Ollama" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Azure AI Foundry" })).toBeVisible();

  await page.getByRole("button", { name: "Provider credentials" }).click();
  await expect(page.getByRole("cell", { name: "****cret" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "api_key" })).toBeVisible();
  await expect(page.getByLabel("Secret value")).toHaveCount(0);

  await page.getByRole("button", { name: "Models and prices" }).click();
  await expect(page.getByText("local_ollama_default")).toBeVisible();
  await expect(page.getByText("azure_foundry_gpt_4o_mini")).toBeVisible();

  await page.getByRole("button", { name: "Routing policies" }).click();
  await expect(page.getByText("Routing policy chooses the model")).toBeVisible();
  await expect(page.getByText("default:free:default")).toBeVisible();

  await page.getByRole("button", { name: "User groups" }).click();
  await expect(page.getByRole("cell", { name: "Admins" }).first()).toBeVisible();

  await page.getByRole("button", { name: "Import from Ollama registry" }).click();
  await expect(page.getByRole("heading", { name: "Import from Ollama registry" })).toBeVisible();
  await expect(page.getByLabel("Ollama model tag")).toBeVisible();

  await page.getByRole("button", { name: "Local Ollama models" }).click();
  await expect(page.getByRole("cell", { name: /qwen3:1\.7b/ }).first()).toBeVisible();
  await expect(page.getByText("Default model cannot be disabled or removed.")).toBeVisible();

  await page.getByRole("button", { name: "Admin audit" }).click();
  await expect(page.getByText("ai_task_route_policy: default:free:default")).toBeVisible();
});

test("admin edit forms replace their grids and save returns to the updated grid", async ({ page }) => {
  let providers = dashboard.providers.map((provider) => ({ ...provider }));
  const currentDashboard = () => ({ ...dashboard, providers });

  await page.route("**/v1/admin/ai-models/providers", async (route) => {
    const input = route.request().postDataJSON() as typeof dashboard.providers[number] & { reason?: string };
    await new Promise((resolve) => setTimeout(resolve, 200));
    providers = providers.map((provider) => provider.provider_code === input.provider_code
      ? {
        ...provider,
        ...input,
        updated_at: "2026-08-15T16:00:00Z"
      }
      : provider);
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(providers.find((provider) => provider.provider_code === input.provider_code))
    });
  });
  await page.route("**/v1/admin/ai-models", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(currentDashboard()) });
  });
  await page.route("**/v1/admin/users?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: dashboard.users, total: 1, limit: 25, offset: 0 })
    });
  });
  await page.route("**/v1/admin/ai-models/ollama/models", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ base_url: "http://127.0.0.1:11434", models: [] })
    });
  });

  await page.addInitScript((user) => {
    window.localStorage.setItem("aj_frontend_lang", "en");
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
  }, adminUser);

  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto("/app/admin", { waitUntil: "domcontentloaded" });

  const editScenarios = [
    { menu: null, rowText: "Admin User", formHeading: "Edit user" },
    { menu: "Providers", rowText: "Local Ollama", formHeading: "Edit model provider" },
    { menu: "Models and prices", rowText: "local_ollama_default", formHeading: "Edit model profile" },
    { menu: "Provider credentials", rowText: "****cret", formHeading: "Edit" },
    { menu: "User groups", rowText: "Admins", formHeading: "Edit user group" },
    { menu: "Routing policies", rowText: "default:free:default", formHeading: "Edit routing policy" }
  ];

  for (const scenario of editScenarios) {
    if (scenario.menu) {
      await page.getByRole("button", { name: scenario.menu }).click();
    }
    const row = page.getByRole("row").filter({ hasText: scenario.rowText }).first();
    await expect(row).toBeVisible();
    await row.getByRole("button", { name: "Edit", exact: true }).click();
    await expect(page.getByRole("heading", { name: scenario.formHeading, exact: true })).toBeVisible();
    await expect(page.locator(".admin-content table")).toHaveCount(0);
    await expect(page.locator(".admin-form-stack")).toBeFocused();
    await expect(page.getByRole("button", { name: scenario.menu ?? "Users" })).toBeVisible();
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(page.locator(".admin-form-stack")).toHaveCount(0);
    await expect(row).toBeVisible();
  }

  await page.getByRole("button", { name: "Providers" }).click();
  const providerRow = page.getByRole("row").filter({ hasText: "Azure AI Foundry" });
  await providerRow.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(page.locator(".admin-content table")).toHaveCount(0);
  await page.getByLabel("Display name").fill("Azure AI Foundry Updated");
  await page.getByLabel("Reason").fill("Synthetic E2E update for issue 618.");

  await mkdir("output/playwright/issue-618", { recursive: true });
  await page.screenshot({ path: "output/playwright/issue-618/01-provider-edit-form-grid-hidden.png", fullPage: true });
  const saveProviderButton = page.getByRole("button", { name: "Save provider" });
  await saveProviderButton.click();
  await expect(saveProviderButton).toBeDisabled();

  await expect(page.getByRole("heading", { name: "Edit model provider" })).toHaveCount(0);
  await expect(page.getByRole("cell", { name: "Azure AI Foundry Updated" })).toBeVisible();
  await expect(page.locator(".admin-content table")).toBeVisible();
  await page.screenshot({ path: "output/playwright/issue-618/02-provider-save-returns-updated-grid.png", fullPage: true });
});

test("admin can set an Ollama model as default and remove the previous non-default model", async ({ page }) => {
  let profiles = [
    { ...dashboard.profiles[0], is_default_for_free: true },
    {
      model_profile_id: "local_ollama_qwen4b",
      provider_id: "local_ollama",
      model_code: "qwen3:4b",
      deployment_name: "qwen3:4b",
      context_window_tokens: 0,
      input_price_per_1m: 0,
      cached_input_price_per_1m: 0,
      output_price_per_1m: 0,
      billing_currency: "EUR",
      effective_from: null,
      effective_to: null,
      eu_data_zone_capable: true,
      is_default_for_free: false,
      enabled: true,
      created_at: "2026-07-03T10:00:00Z",
      updated_at: "2026-07-03T10:00:00Z"
    }
  ];
  let policies = dashboard.policies.map((policy) => ({ ...policy, preferred_local_model_profile_id: "local_ollama_default" }));
  let removedModel = "";
  const currentDashboard = () => ({
    ...dashboard,
    profiles,
    policies
  });
  const currentInventory = () => ({
    base_url: "http://127.0.0.1:11434",
    models: [
      {
        name: "qwen3:1.7b",
        model: "qwen3:1.7b",
        modified_at: "2026-06-27T10:00:00Z",
        size: 1700000000,
        digest: "sha256:qwen",
        details: {},
        installed: true,
        configured_profile_ids: ["local_ollama_default"],
        active_policy_ids: policies.filter((policy) => policy.preferred_local_model_profile_id === "local_ollama_default").map((policy) => policy.policy_id),
        is_default: profiles.some((profile) => profile.model_code === "qwen3:1.7b" && profile.is_default_for_free),
        is_running: false,
        removable: !profiles.some((profile) => profile.model_code === "qwen3:1.7b" && profile.is_default_for_free),
        removal_blockers: profiles.some((profile) => profile.model_code === "qwen3:1.7b" && profile.is_default_for_free)
          ? ["Profile local_ollama_default is marked as the free/default local model."]
          : []
      },
      {
        name: "qwen3:4b",
        model: "qwen3:4b",
        modified_at: "2026-07-03T10:00:00Z",
        size: 4000000000,
        digest: "sha256:qwen4b",
        details: {},
        installed: true,
        configured_profile_ids: ["local_ollama_qwen4b"],
        active_policy_ids: policies.filter((policy) => policy.preferred_local_model_profile_id === "local_ollama_qwen4b").map((policy) => policy.policy_id),
        is_default: profiles.some((profile) => profile.model_code === "qwen3:4b" && profile.is_default_for_free),
        is_running: false,
        removable: !profiles.some((profile) => profile.model_code === "qwen3:4b" && profile.is_default_for_free),
        removal_blockers: profiles.some((profile) => profile.model_code === "qwen3:4b" && profile.is_default_for_free)
          ? ["Profile local_ollama_qwen4b is marked as the free/default local model."]
          : []
      }
    ].filter((model) => model.name !== removedModel)
  });

  await page.route("**/v1/admin/ai-models", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(currentDashboard()) });
  });
  await page.route("**/v1/admin/users?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: dashboard.users, total: 1, limit: 25, offset: 0 })
    });
  });
  await page.route("**/v1/admin/ai-models/ollama/models", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(currentInventory()) });
  });
  await page.route("**/v1/admin/ai-models/ollama/models/**/default", async (route) => {
    profiles = profiles.map((profile) => ({
      ...profile,
      is_default_for_free: profile.model_code === "qwen3:4b",
      enabled: profile.model_code === "qwen3:4b" ? true : profile.enabled
    }));
    policies = policies.map((policy) => ({ ...policy, preferred_local_model_profile_id: "local_ollama_qwen4b" }));
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(profiles.find((profile) => profile.model_code === "qwen3:4b"))
    });
  });
  await page.route("**/v1/admin/ai-models/ollama/models/*", async (route) => {
    removedModel = decodeURIComponent(route.request().url().split("/ollama/models/")[1] ?? "");
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        job_id: "remove-job-1",
        action: "remove",
        model: removedModel,
        status: "queued",
        message: "queued",
        created_at: "2026-07-03T10:10:00Z",
        updated_at: "2026-07-03T10:10:00Z"
      })
    });
  });

  await page.addInitScript((user) => {
    window.localStorage.setItem("aj_frontend_lang", "en");
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
  }, adminUser);

  await page.goto("/app/admin", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Local Ollama models" }).click();
  const firstDefaultRow = page.getByRole("row").filter({ hasText: "qwen3:1.7b" });
  await expect(firstDefaultRow.locator(".admin-default-model-name")).toBeVisible();
  await firstDefaultRow.screenshot({ path: "output/playwright/codex-462/01-before-default-change.png" });

  const qwen4bRow = page.getByRole("row").filter({ hasText: "qwen3:4b" });
  await qwen4bRow.getByRole("button", { name: "Set as default" }).click();
  await expect(qwen4bRow.locator(".admin-default-model-name")).toContainText("qwen3:4b");
  await expect(qwen4bRow.getByRole("button", { name: "Set as default" })).toBeDisabled();
  await qwen4bRow.screenshot({ path: "output/playwright/codex-462/02-after-default-change.png" });

  const oldDefaultRow = page.getByRole("row").filter({ hasText: "qwen3:1.7b" });
  await expect(oldDefaultRow.getByRole("button", { name: "Remove model" })).toBeEnabled();
  await oldDefaultRow.getByRole("button", { name: "Remove model" }).click();
  await expect(page.getByText("Ollama model removal was started.")).toBeVisible();
  expect(removedModel).toBe("qwen3:1.7b");
  await qwen4bRow.screenshot({ path: "output/playwright/codex-462/03-after-non-default-remove.png" });
});

test("admin local Ollama table loads on menu click and removes not-installed configured models", async ({ page }) => {
  let removedModel = "";
  let ollamaFetchCount = 0;
  const currentInventory = () => ({
    base_url: "http://127.0.0.1:11434",
    models: [
      {
        name: "qwen3:4b",
        model: "qwen3:4b",
        modified_at: "2026-07-03T10:00:00Z",
        size: 2300000000,
        digest: "sha256:qwen4b",
        details: {},
        installed: true,
        configured_profile_ids: ["local_ollama_qwen4b"],
        active_policy_ids: ["default:free:default"],
        is_default: true,
        is_running: false,
        removable: false,
        removal_blockers: ["Profile local_ollama_qwen4b is marked as the free/default local model."]
      },
      {
        name: "Qwen3:4b",
        model: "Qwen3:4b",
        modified_at: "",
        size: 0,
        digest: "",
        details: { configured_only: true },
        installed: false,
        configured_profile_ids: ["local_ollama_missing_qwen4b"],
        active_policy_ids: [],
        is_default: false,
        is_running: false,
        removable: true,
        removal_blockers: ["Model is configured in JurisDigta but is not installed in Ollama."]
      }
    ].filter((model) => model.name !== removedModel)
  });

  await page.route("**/v1/admin/ai-models", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(dashboard) });
  });
  await page.route("**/v1/admin/users?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: dashboard.users, total: 1, limit: 25, offset: 0 })
    });
  });
  await page.route("**/v1/admin/ai-models/ollama/models", async (route) => {
    ollamaFetchCount += 1;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(currentInventory()) });
  });
  await page.route("**/v1/admin/ai-models/ollama/models/*", async (route) => {
    removedModel = decodeURIComponent(route.request().url().split("/ollama/models/")[1] ?? "");
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        job_id: "remove-missing-job-1",
        action: "remove",
        model: removedModel,
        status: "succeeded",
        message: "Configured Ollama model profile removed; model was not installed in Ollama.",
        created_at: "2026-07-03T10:10:00Z",
        updated_at: "2026-07-03T10:10:00Z"
      })
    });
  });

  await page.addInitScript((user) => {
    window.localStorage.setItem("aj_frontend_lang", "en");
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
  }, adminUser);

  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto("/app/admin", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Local Ollama models" }).click();
  await expect(page.getByRole("heading", { name: "Local Ollama models" })).toBeVisible();
  await expect.poll(() => ollamaFetchCount).toBeGreaterThan(0);
  await page.screenshot({ path: "output/playwright/codex-468/01-ollama-menu-loads-table.png", fullPage: true });

  const missingRow = page.getByRole("row", { name: /^Qwen3:4b\s+Not installed/ });
  await expect(missingRow).toContainText("Not installed");
  await expect(missingRow.locator(".admin-default-model-name")).toHaveCount(0);
  await expect(missingRow.getByRole("button", { name: "Set as default" })).toBeDisabled();
  await expect(missingRow.getByRole("button", { name: "Disable model" })).toBeEnabled();
  await expect(missingRow.getByRole("button", { name: "Remove model" })).toBeEnabled();
  await missingRow.screenshot({ path: "output/playwright/codex-468/02-not-installed-removable.png" });

  await missingRow.getByRole("button", { name: "Disable model" }).click();
  await expect(page.getByText("Ollama model removal was started.")).toBeVisible();
  await expect(page.getByRole("row", { name: /^Qwen3:4b\s+Not installed/ })).toHaveCount(0);
  expect(removedModel).toBe("Qwen3:4b");
  await page.screenshot({ path: "output/playwright/codex-468/03-after-disable-removes-row.png", fullPage: true });
});

test.describe("provider credentials lifecycle", () => {
  test("logs in, opens Admin Provider credentials, adds and updates a provider", async ({ page }) => {
    let providers = dashboard.providers.map((provider) => ({ ...provider }));
    const currentDashboard = () => ({
      ...dashboard,
      providers
    });

    await page.route("**/v1/users/sign-in", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          user_id: adminUser.userId,
          email: adminUser.email,
          full_name: adminUser.name,
          role: adminUser.role,
          is_enabled: true,
          device_auth_token: adminUser.deviceAuthToken
        })
      });
    });

    await page.route("**/v1/admin/ai-models/providers", async (route) => {
      const input = route.request().postDataJSON() as typeof dashboard.providers[number] & { reason?: string };
      const existingIndex = providers.findIndex((provider) => provider.provider_code === input.provider_code);
      const savedProvider = {
        provider_id: existingIndex >= 0 ? providers[existingIndex]!.provider_id : input.provider_code,
        provider_code: input.provider_code,
        provider_type: input.provider_type,
        display_name: input.display_name,
        base_url: input.base_url,
        api_version: input.api_version ?? "",
        region: input.region,
        data_zone: input.data_zone,
        is_external: input.is_external,
        is_local: input.is_local,
        health_check_url: input.health_check_url,
        enabled: input.enabled,
        created_at: existingIndex >= 0 ? providers[existingIndex]!.created_at : "2026-07-03T10:00:00Z",
        updated_at: "2026-07-03T10:10:00Z",
        deleted_at: null,
        deleted_by_admin_user_id: "",
        deleted_reason: ""
      };
      providers = existingIndex >= 0
        ? providers.map((provider, index) => (index === existingIndex ? savedProvider : provider))
        : [...providers, savedProvider];
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(savedProvider) });
    });

    await page.route("**/v1/admin/ai-models", async (route) => {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(currentDashboard()) });
    });

    await page.route("**/v1/admin/users?**", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ items: dashboard.users, total: 1, limit: 25, offset: 0 })
      });
    });

    await page.route("**/v1/admin/ai-models/ollama/models", async (route) => {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ base_url: "http://127.0.0.1:11434", models: [] }) });
    });

    await page.addInitScript(() => {
      window.localStorage.setItem("aj_frontend_lang", "en");
    });

    await page.goto("/auth", { waitUntil: "domcontentloaded" });
    await page.getByLabel("Work email").fill(adminUser.email);
    await page.getByLabel("Password").fill("admin123");
    const signInResponse = page.waitForResponse((response) =>
      response.url().includes("/v1/users/sign-in") && response.status() === 200
    );
    await page.getByRole("button", { name: "Sign in" }).click();
    await signInResponse;
    await page.goto("/app/admin", { waitUntil: "domcontentloaded" });

    await expect(page).toHaveURL(/\/app\/admin/);
    await page.screenshot({ path: "test-results/codex-455-screenshots/01-admin-page.png", fullPage: true });
    await expect(page.getByRole("button", { name: "Providers" })).toBeVisible();
    await page.getByRole("button", { name: "Providers" }).click();
    await expect(page.getByRole("button", { name: "Providers" })).toHaveClass(/is-active/);
    await expect(page.getByRole("heading", { name: "Providers" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "Local Ollama" })).toBeVisible();
    await page.screenshot({ path: "test-results/codex-455-screenshots/02-provider-credentials-table.png", fullPage: true });

    await page.getByRole("button", { name: "Add provider" }).click();
    await expect(page.getByRole("heading", { name: "Add model provider" })).toBeVisible();
    await page.getByLabel("Provider code").fill("test_provider");
    await page.getByLabel("Provider type").selectOption("openai_compatible");
    await page.getByLabel("Display name").fill("Test Provider");
    await page.getByLabel("Base URL").fill("https://provider.example.test/v1");
    await page.getByLabel("API version").fill("2026-07-03");
    await page.getByLabel("Region").fill("eu");
    await page.getByLabel("Data zone").fill("eu");
    await page.getByLabel("Health URL").fill("https://provider.example.test/health");
    await page.getByLabel("Reason").fill("Add provider from E2E.");
    await page.getByRole("button", { name: "Save provider" }).click();

    await expect(page.getByRole("heading", { name: "Add model provider" })).toBeHidden();
    await expect(page.getByRole("cell", { name: "Test Provider" })).toBeVisible();

    const testProviderRow = page.getByRole("row").filter({ hasText: "Test Provider" });
    await testProviderRow.getByRole("button", { name: "Edit" }).click();
    await expect(page.getByRole("heading", { name: "Edit model provider" })).toBeVisible();
    await page.addStyleTag({ content: ".site-header { display: none !important; }" });
    await page.getByRole("heading", { name: "Edit model provider" }).scrollIntoViewIfNeeded();
    await page.locator(".admin-form-stack").screenshot({ path: "test-results/codex-455-screenshots/03-provider-credentials-edit-form.png" });
    await page.getByLabel("Display name").fill("Updated Test Provider");
    await page.getByLabel("Reason").fill("Update provider from E2E.");
    await page.getByRole("button", { name: "Save provider" }).click();

    await expect(page.getByRole("heading", { name: "Edit model provider" })).toBeHidden();
    await expect(page.getByRole("cell", { name: "Updated Test Provider" })).toBeVisible();
    await expect(page.getByText("Test Provider", { exact: true })).toBeHidden();
  });
});
