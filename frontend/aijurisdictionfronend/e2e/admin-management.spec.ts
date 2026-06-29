import { expect, test } from "@playwright/test";

const adminUser = {
  userId: "admin-1",
  deviceId: "web-device-1",
  deviceAuthToken: "device-token-1",
  email: "admin@example.test",
  name: "Admin User",
  role: "admin",
  isEnabled: true
};

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
      updated_at: "2026-06-27T10:00:00Z"
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
      updated_at: "2026-06-27T10:00:00Z"
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
  credentials: [],
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

  await page.goto("/app/admin", { waitUntil: "domcontentloaded" });

  await expect(page.getByText("Admin User (admin@example.test)")).toBeVisible();
  await expect(page.getByText("1-1 of 1")).toBeVisible();
  expect(adminHeader).toBe("admin-1");
  expect(deviceHeader).toBe("device-token-1");

  await page.getByRole("button", { name: "Providers" }).click();
  await expect(page.getByRole("cell", { name: "Local Ollama" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Azure AI Foundry" })).toBeVisible();

  await page.getByRole("button", { name: "Models and prices" }).click();
  await expect(page.getByText("local_ollama_default")).toBeVisible();
  await expect(page.getByText("azure_foundry_gpt_4o_mini")).toBeVisible();

  await page.getByRole("button", { name: "Routing policies" }).click();
  await expect(page.getByText("Routing policy chooses the model")).toBeVisible();
  await expect(page.getByText("default:free:default")).toBeVisible();

  await page.getByRole("button", { name: "User groups" }).click();
  await expect(page.getByRole("cell", { name: "Admins" }).first()).toBeVisible();

  await page.getByRole("button", { name: "Local Ollama models" }).click();
  await expect(page.getByRole("cell", { name: /qwen3:1\.7b/ }).first()).toBeVisible();

  await page.getByRole("button", { name: "Admin audit" }).click();
  await expect(page.getByText("ai_task_route_policy: default:free:default")).toBeVisible();
});
