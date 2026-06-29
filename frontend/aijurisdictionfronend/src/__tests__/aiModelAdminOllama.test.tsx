// @vitest-environment jsdom

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AIModelAdmin from "../pages/AIModelAdmin";

const apiMocks = vi.hoisted(() => ({
  fetchAIModelAdminDashboard: vi.fn(),
  fetchAdminUsers: vi.fn(),
  fetchOllamaModels: vi.fn(),
  importOllamaModel: vi.fn(),
  removeOllamaModel: vi.fn(),
  upsertAIModelProvider: vi.fn(),
  upsertAIModelProfile: vi.fn(),
  upsertAIModelGroup: vi.fn(),
  addAIModelGroupMember: vi.fn(),
  upsertAIModelRoutePolicy: vi.fn(),
  upsertAIModelCredential: vi.fn(),
  updateAdminUser: vi.fn()
}));

vi.mock("../api/adminModelClient", () => apiMocks);

vi.mock("../auth/webAuth", () => ({
  useAuth: () => ({
    user: {
      userId: "admin-1",
      email: "admin@example.com",
      name: "Admin User",
      role: "admin",
      deviceId: "web-device-1",
      deviceAuthToken: "device-token-1"
    }
  })
}));

const translateKey = (key: string, values?: Record<string, string | number>) => {
  if (key === "adminPaginationSummary" && values) {
    return `${values.start}-${values.end} of ${values.total}`;
  }
  return key;
};

vi.mock("../components/LanguageProvider", () => ({
  useLanguage: () => ({
    t: translateKey
  })
}));

const dashboard = {
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
      task_type: "default",
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
  groups: [],
  memberships: [],
  users: [
    {
      user_id: "admin-1",
      phone_number: null,
      email: "admin@example.com",
      full_name: "Admin User",
      role: "admin",
      is_enabled: true,
      created_at: "2026-06-27T10:00:00Z"
    }
  ],
  users_page: {
    total: 1,
    limit: 25,
    offset: 0
  },
  audit_events: [],
  route_priority: [],
  compliance_notes: [],
  grafana_url: "https://admin.jurisdigta.eu/grafana/"
};

const inventory = {
  base_url: "http://127.0.0.1:11434",
  models: [
    {
      name: "qwen3:1.7b",
      model: "qwen3:1.7b",
      modified_at: "2026-06-27T10:00:00Z",
      size: 17_000_000_000,
      digest: "sha256:default",
      details: {},
      installed: true,
      configured_profile_ids: ["local_ollama_default"],
      active_policy_ids: ["default:free:default"],
      is_default: true,
      is_running: false,
      removable: false,
      removal_blockers: ["Profile local_ollama_default is the seeded system local default."]
    },
    {
      name: "llama3.2:3b",
      model: "llama3.2:3b",
      modified_at: "2026-06-27T11:00:00Z",
      size: 2_000_000_000,
      digest: "sha256:unused",
      details: {},
      installed: true,
      configured_profile_ids: [],
      active_policy_ids: [],
      is_default: false,
      is_running: false,
      removable: true,
      removal_blockers: []
    }
  ]
};

describe("AIModelAdmin Ollama management", () => {
  beforeEach(() => {
    apiMocks.fetchAIModelAdminDashboard.mockResolvedValue(dashboard);
    apiMocks.fetchAdminUsers.mockResolvedValue({ items: dashboard.users, total: 1, limit: 25, offset: 0 });
    apiMocks.fetchOllamaModels.mockResolvedValue(inventory);
    apiMocks.importOllamaModel.mockResolvedValue({ job_id: "job-1", action: "pull", model: "gemma3:4b", status: "queued" });
    apiMocks.removeOllamaModel.mockResolvedValue({ job_id: "job-2", action: "remove", model: "llama3.2:3b", status: "queued" });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders Ollama inventory and disables remove for protected default models", async () => {
    const user = userEvent.setup();
    render(<AIModelAdmin />);

    await user.click(await screen.findByRole("button", { name: /adminOllamaTitle/ }));

    expect(await screen.findByText("qwen3:1.7b")).toBeDefined();
    expect(screen.getByText("llama3.2:3b")).toBeDefined();
    expect(screen.getByText("local_ollama_default")).toBeDefined();

    const removeButtons = screen.getAllByRole("button", { name: /adminOllamaRemove/ });
    expect(removeButtons.at(0)?.hasAttribute("disabled")).toBe(true);
  });

  it("shows seeded providers, profiles, users, and routing guidance", async () => {
    const user = userEvent.setup();
    render(<AIModelAdmin />);

    expect(await screen.findByText("Admin User (admin@example.com)")).toBeDefined();
    expect(screen.getByText("1-1 of 1")).toBeDefined();

    await user.click(screen.getByRole("button", { name: /adminProvidersTitle/ }));
    expect(await screen.findByText("Local Ollama")).toBeDefined();
    expect(screen.getByText("Azure AI Foundry")).toBeDefined();

    await user.click(screen.getByRole("button", { name: /adminProfilesTitle/ }));
    expect(await screen.findByText("local_ollama_default")).toBeDefined();
    expect(screen.getByText("azure_foundry_gpt_4o_mini")).toBeDefined();

    await user.click(screen.getByRole("button", { name: /adminPoliciesTitle/ }));
    expect(await screen.findByText("adminPolicyHelp")).toBeDefined();
  });

  it("lets admins update and disable routing policies", async () => {
    const user = userEvent.setup();
    render(<AIModelAdmin />);

    await user.click(await screen.findByRole("button", { name: /adminPoliciesTitle/ }));
    await user.click(await screen.findByRole("button", { name: /adminDisablePolicy/ }));

    await waitFor(() => {
      expect(apiMocks.upsertAIModelRoutePolicy).toHaveBeenCalledWith(
        expect.objectContaining({ userId: "admin-1" }),
        expect.objectContaining({
          policy_id: "default:free:default",
          enabled: false,
          reason: "Disable route policy from admin UI."
        })
      );
    });

    await user.click(screen.getByRole("button", { name: /adminEdit/ }));
    expect((screen.getByLabelText("adminPlanCode") as HTMLInputElement).value).toBe("free");
  });

  it("lets admins disable model profiles and set a local free default", async () => {
    const user = userEvent.setup();
    const profileDashboard = {
      ...dashboard,
      profiles: [
        ...dashboard.profiles,
        {
          model_profile_id: "local_ollama_llama32",
          provider_id: "local_ollama",
          model_code: "llama3.2:3b",
          deployment_name: "llama3.2:3b",
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
          created_at: "2026-06-27T10:00:00Z",
          updated_at: "2026-06-27T10:00:00Z"
        }
      ]
    };
    apiMocks.fetchAIModelAdminDashboard.mockResolvedValue(profileDashboard);
    render(<AIModelAdmin />);

    await user.click(await screen.findByRole("button", { name: /adminProfilesTitle/ }));
    await user.click(screen.getAllByRole("button", { name: /adminDisableModel/ }).at(0) as HTMLElement);

    await waitFor(() => {
      expect(apiMocks.upsertAIModelProfile).toHaveBeenCalledWith(
        expect.objectContaining({ userId: "admin-1" }),
        expect.objectContaining({
          model_profile_id: "local_ollama_default",
          enabled: false,
          reason: "Disable model profile from admin UI."
        })
      );
    });

    const defaultButtons = screen.getAllByRole("button", { name: /adminSetFreeDefault/ });
    const enabledDefaultButton = defaultButtons.find((button) => !button.hasAttribute("disabled"));
    expect(enabledDefaultButton).toBeDefined();
    await user.click(enabledDefaultButton as HTMLElement);

    await waitFor(() => {
      expect(apiMocks.upsertAIModelProfile).toHaveBeenCalledWith(
        expect.objectContaining({ userId: "admin-1" }),
        expect.objectContaining({
          model_profile_id: "local_ollama_llama32",
          enabled: true,
          is_default_for_free: true,
          reason: "Set as the default local model for free accounts."
        })
      );
    });
  });

  it("starts import and safe remove jobs", async () => {
    const user = userEvent.setup();
    render(<AIModelAdmin />);

    await user.click(await screen.findByRole("button", { name: /adminOllamaTitle/ }));
    await user.type(screen.getByLabelText("adminOllamaModelTag"), "gemma3:4b");
    await user.type(screen.getByLabelText("adminReason"), "Add fallback model");
    await user.click(screen.getByRole("button", { name: /adminOllamaImport/ }));

    await waitFor(() => {
      expect(apiMocks.importOllamaModel).toHaveBeenCalledWith(
        expect.objectContaining({ userId: "admin-1", deviceAuthToken: "device-token-1" }),
        "gemma3:4b",
        "Add fallback model"
      );
    });

    await user.type(screen.getByLabelText("adminOllamaActionReason"), "Remove unused model");
    const removeButtons = screen.getAllByRole("button", { name: /adminOllamaRemove/ });
    const unusedRemoveButton = removeButtons.at(1);
    expect(unusedRemoveButton).toBeDefined();
    await user.click(unusedRemoveButton as HTMLElement);

    await waitFor(() => {
      expect(apiMocks.removeOllamaModel).toHaveBeenCalledWith(
        expect.objectContaining({ userId: "admin-1", deviceAuthToken: "device-token-1" }),
        "llama3.2:3b",
        "Remove unused model"
      );
    });
  });

  it("disables configured Ollama model profiles from the runtime inventory", async () => {
    const user = userEvent.setup();
    render(<AIModelAdmin />);

    await user.click(await screen.findByRole("button", { name: /adminOllamaTitle/ }));
    await user.type(screen.getByLabelText("adminOllamaActionReason"), "Disable imported local model");
    const disableButtons = screen.getAllByRole("button", { name: /adminOllamaDisable/ });
    await user.click(disableButtons.at(0) as HTMLElement);

    await waitFor(() => {
      expect(apiMocks.upsertAIModelProfile).toHaveBeenCalledWith(
        expect.objectContaining({ userId: "admin-1", deviceAuthToken: "device-token-1" }),
        expect.objectContaining({
          model_profile_id: "local_ollama_default",
          enabled: false,
          reason: "Disable imported local model"
        })
      );
    });
  });
});
