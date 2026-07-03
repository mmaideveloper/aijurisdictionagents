// @vitest-environment jsdom

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AIModelAdmin from "../pages/AIModelAdmin";

const apiMocks = vi.hoisted(() => ({
  fetchAIModelAdminDashboard: vi.fn(),
  fetchAdminUsers: vi.fn(),
  searchAIModelAssignmentUsers: vi.fn(),
  fetchAIModelUserOverride: vi.fn(),
  upsertAIModelUserOverride: vi.fn(),
  disableAIModelUserOverride: vi.fn(),
  fetchOllamaModels: vi.fn(),
  deleteAIModelProvider: vi.fn(),
  deleteAIModelProfile: vi.fn(),
  deleteAIModelGroup: vi.fn(),
  deleteAIModelRoutePolicy: vi.fn(),
  importOllamaModel: vi.fn(),
  removeOllamaModel: vi.fn(),
  upsertAIModelProvider: vi.fn(),
  upsertAIModelProfile: vi.fn(),
  upsertAIModelGroup: vi.fn(),
  addAIModelGroupMember: vi.fn(),
  upsertAIModelRoutePolicy: vi.fn(),
  upsertAIModelCredential: vi.fn(),
  patchAIModelCredential: vi.fn(),
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
      updated_at: "2026-06-27T10:00:00Z",
      deleted_at: null,
      deleted_by_admin_user_id: "",
      deleted_reason: ""
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
      updated_at: "2026-06-27T10:00:00Z",
      deleted_at: null,
      deleted_by_admin_user_id: "",
      deleted_reason: ""
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
      updated_at: "2026-06-27T10:00:00Z",
      deleted_at: null,
      deleted_by_admin_user_id: "",
      deleted_reason: ""
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
    apiMocks.searchAIModelAssignmentUsers.mockResolvedValue({ items: dashboard.users, total: 1, limit: 25 });
    apiMocks.fetchAIModelUserOverride.mockResolvedValue({
      user: dashboard.users[0],
      override: null,
      effective_route: {
        route_type: "free_local",
        task_type: "default",
        plan_code: "free",
        provider_id: "local_ollama",
        provider_code: "local_ollama",
        provider_display_name: "Local Ollama",
        model_profile_id: "local_ollama_default",
        model_code: "qwen3:1.7b",
        deployment_name: "qwen3:1.7b",
        is_external: false,
        is_local: true,
        requires_external_ack: false,
        reason: "Default route"
      }
    });
    apiMocks.upsertAIModelUserOverride.mockResolvedValue({
      user: dashboard.users[0],
      override: {
        override_id: "override-1",
        user_id: "admin-1",
        model_profile_id: "azure_foundry_gpt_4o_mini",
        enabled: true,
        created_by_admin_user_id: "admin-1",
        updated_by_admin_user_id: "admin-1",
        disabled_by_admin_user_id: "",
        created_reason: "Assign external model",
        updated_reason: "Assign external model",
        disabled_reason: "",
        created_at: "2026-06-29T10:00:00Z",
        updated_at: "2026-06-29T10:00:00Z",
        disabled_at: null
      },
      effective_route: {
        route_type: "user_override_external",
        task_type: "default",
        plan_code: "free",
        provider_id: "azure_foundry",
        provider_code: "azure_foundry",
        provider_display_name: "Azure AI Foundry",
        model_profile_id: "azure_foundry_gpt_4o_mini",
        model_code: "gpt-4o-mini",
        deployment_name: "gpt-4o-mini",
        is_external: true,
        is_local: false,
        requires_external_ack: false,
        reason: "Admin override"
      }
    });
    apiMocks.fetchOllamaModels.mockResolvedValue(inventory);
    apiMocks.importOllamaModel.mockResolvedValue({ job_id: "job-1", action: "pull", model: "gemma3:4b", status: "queued" });
    apiMocks.removeOllamaModel.mockResolvedValue({ job_id: "job-2", action: "remove", model: "llama3.2:3b", status: "queued" });
    apiMocks.upsertAIModelProvider.mockResolvedValue(dashboard.providers[1]);
    apiMocks.deleteAIModelProvider.mockResolvedValue({ ...dashboard.providers[1], enabled: false, deleted_at: "2026-07-03T10:10:00Z" });
    apiMocks.deleteAIModelProfile.mockResolvedValue({ ...dashboard.profiles[1], enabled: false, deleted_at: "2026-07-03T10:10:00Z" });
    apiMocks.deleteAIModelGroup.mockResolvedValue({
      model_group_id: "paid",
      group_code: "paid",
      display_name: "Paid",
      priority: 10,
      enabled: false,
      created_at: "2026-06-27T10:00:00Z",
      updated_at: "2026-07-03T10:10:00Z",
      deleted_at: "2026-07-03T10:10:00Z",
      deleted_by_admin_user_id: "admin-1",
      deleted_reason: "Test delete"
    });
    apiMocks.deleteAIModelRoutePolicy.mockResolvedValue({ ...dashboard.policies[0], enabled: false, deleted_at: "2026-07-03T10:10:00Z" });
    apiMocks.upsertAIModelProfile.mockImplementation((_, input) => {
      const existingProfile =
        dashboard.profiles.find((profile) => profile.model_profile_id === input.model_profile_id) ??
        dashboard.profiles.find((profile) => profile.provider_id === input.provider_id) ??
        dashboard.profiles[0]!;
      return Promise.resolve({
        ...existingProfile,
        ...input,
        model_profile_id: input.model_profile_id ?? `${input.provider_id}:${input.model_code}`,
        created_at: existingProfile.created_at,
        updated_at: "2026-06-30T10:00:00Z"
      });
    });
    apiMocks.patchAIModelCredential.mockResolvedValue(dashboard.credentials[0]);
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
    expect(screen.getByText("adminOllamaDefaultWarning")).toBeDefined();

    const removeButtons = screen.getAllByRole("button", { name: /adminOllamaRemove/ });
    expect(removeButtons.at(0)?.hasAttribute("disabled")).toBe(true);
    expect(removeButtons.at(1)?.hasAttribute("disabled")).toBe(false);
    expect(screen.getAllByRole("button", { name: /adminOllamaSetDefault/ })).toHaveLength(1);
  });

  it("shows a user edit form and hides it after save or cancel", async () => {
    const user = userEvent.setup();
    render(<AIModelAdmin />);

    await user.click(await screen.findByRole("button", { name: /adminEdit/ }));
    expect(await screen.findByRole("heading", { name: /adminUserEditTitle/ })).toBeDefined();
    await user.selectOptions(screen.getByLabelText("adminRole"), "user");
    await user.type(screen.getByLabelText("adminReason"), "Update user from table.");
    await user.click(screen.getByRole("button", { name: /adminSaveUser/ }));

    await waitFor(() => {
      expect(apiMocks.updateAdminUser).toHaveBeenCalledWith(
        expect.objectContaining({ userId: "admin-1" }),
        "admin-1",
        {
          role: "user",
          is_enabled: true,
          reason: "Update user from table."
        }
      );
    });
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: /adminUserEditTitle/ })).toBeNull();
    });

    await user.click(screen.getByRole("button", { name: /adminEdit/ }));
    await user.click(screen.getByRole("button", { name: /adminCancel/ }));
    expect(screen.queryByRole("heading", { name: /adminUserEditTitle/ })).toBeNull();
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
    expect(screen.getByText(/adminCurrentFreeModel/)).toBeDefined();
    expect(screen.getByText(/qwen3:1.7b \(Local Ollama\)/)).toBeDefined();

    await user.click(screen.getByRole("button", { name: /adminPoliciesTitle/ }));
    expect(await screen.findByText("adminPolicyHelp")).toBeDefined();
  });

  it("shows provider credentials table first and hides the edit form after save or cancel", async () => {
    const user = userEvent.setup();
    render(<AIModelAdmin />);

    await user.click(await screen.findByRole("button", { name: /adminCredentialsTitle/ }));
    expect(await screen.findByText("Local Ollama")).toBeDefined();
    expect(screen.queryByRole("heading", { name: /adminProviderEditTitle/ })).toBeNull();

    await user.click(screen.getAllByRole("button", { name: /adminEdit/ }).at(1)!);
    expect(await screen.findByRole("heading", { name: /adminProviderEditTitle/ })).toBeDefined();
    const baseUrlInput = screen.getByLabelText("adminBaseUrl") as HTMLInputElement;
    expect(baseUrlInput.value).toBe("");

    await user.type(baseUrlInput, "https://example.openai.azure.com");
    await user.type(screen.getByLabelText("adminReason"), "Configure Azure Foundry endpoint.");
    await user.click(screen.getByRole("button", { name: /adminSaveProvider/ }));

    await waitFor(() => {
      expect(apiMocks.upsertAIModelProvider).toHaveBeenCalledWith(
        expect.objectContaining({ userId: "admin-1" }),
        expect.objectContaining({
          provider_code: "azure_foundry",
          base_url: "https://example.openai.azure.com",
          reason: "Configure Azure Foundry endpoint."
        })
      );
    });
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: /adminProviderEditTitle/ })).toBeNull();
    });

    await user.click(screen.getByRole("button", { name: /adminAddProvider/ }));
    expect(await screen.findByRole("heading", { name: /adminProviderCreateTitle/ })).toBeDefined();
    await user.click(screen.getByRole("button", { name: /adminCancel/ }));
    expect(screen.queryByRole("heading", { name: /adminProviderCreateTitle/ })).toBeNull();
  });

  it("lets admins edit and delete routing policies", async () => {
    const user = userEvent.setup();
    const promptSpy = vi.spyOn(window, "prompt").mockReturnValue("Retire old policy.");
    render(<AIModelAdmin />);

    await user.click(await screen.findByRole("button", { name: /adminPoliciesTitle/ }));
    await user.click(await screen.findByRole("button", { name: /adminEdit/ }));
    expect((screen.getByLabelText("adminPlanCode") as HTMLInputElement).value).toBe("free");
    await user.type(screen.getByLabelText("adminReason"), "Update route policy.");
    await user.click(screen.getByRole("button", { name: /adminSavePolicy/ }));

    await waitFor(() => {
      expect(apiMocks.upsertAIModelRoutePolicy).toHaveBeenCalledWith(
        expect.objectContaining({ userId: "admin-1" }),
        expect.objectContaining({
          policy_id: "default:free:default",
          reason: "Update route policy."
        })
      );
    });

    await user.click(screen.getByRole("button", { name: /adminDelete/ }));
    await waitFor(() => {
      expect(apiMocks.deleteAIModelRoutePolicy).toHaveBeenCalledWith(
        expect.objectContaining({ userId: "admin-1" }),
        "default:free:default",
        { reason: "Retire old policy." }
      );
    });
    promptSpy.mockRestore();
  });

  it("lets admins edit model profiles and set a local free default", async () => {
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
          updated_at: "2026-06-27T10:00:00Z",
          deleted_at: null,
          deleted_by_admin_user_id: "",
          deleted_reason: ""
        }
      ]
    };
    apiMocks.fetchAIModelAdminDashboard.mockResolvedValue(profileDashboard);
    render(<AIModelAdmin />);

    await user.click(await screen.findByRole("button", { name: /adminProfilesTitle/ }));
    await user.click(screen.getAllByRole("button", { name: /adminEdit/ }).at(0) as HTMLElement);
    await user.type(screen.getByLabelText("adminReason"), "Update model profile.");
    await user.click(screen.getByRole("button", { name: /adminSaveProfile/ }));

    await waitFor(() => {
      expect(apiMocks.upsertAIModelProfile).toHaveBeenCalledWith(
        expect.objectContaining({ userId: "admin-1" }),
        expect.objectContaining({
          model_profile_id: "local_ollama_default",
          reason: "Update model profile."
        })
      );
    });

    expect(screen.getAllByRole("button", { name: /adminSetFreeDefault/ })).toHaveLength(1);
    expect(screen.getByText(/qwen3:1.7b \(Local Ollama\)/)).toBeDefined();
    await user.click(screen.getByRole("button", { name: /adminSetFreeDefault/ }));

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
    await waitFor(() => {
      expect(screen.getByText(/llama3.2:3b \(Local Ollama\)/)).toBeDefined();
    });
    expect(screen.getAllByRole("button", { name: /adminSetFreeDefault/ })).toHaveLength(1);
  });

  it("starts import and safe remove jobs", async () => {
    const user = userEvent.setup();
    render(<AIModelAdmin />);

    await user.click(await screen.findByRole("button", { name: /adminOllamaImportTitle/ }));
    await user.type(screen.getByLabelText("adminOllamaModelTag"), "gemma3:4b");
    await user.type(screen.getByLabelText("adminReason"), "Add fallback model");
    await user.click(screen.getByRole("button", { name: /^adminOllamaImport$/ }));

    await waitFor(() => {
      expect(apiMocks.importOllamaModel).toHaveBeenCalledWith(
        expect.objectContaining({ userId: "admin-1", deviceAuthToken: "device-token-1" }),
        "gemma3:4b",
        "Add fallback model"
      );
    });

    await user.click(screen.getByRole("button", { name: /adminOllamaTitle/ }));
    const removeButtons = screen.getAllByRole("button", { name: /adminOllamaRemove/ });
    const unusedRemoveButton = removeButtons.at(1);
    expect(unusedRemoveButton).toBeDefined();
    await user.click(unusedRemoveButton as HTMLElement);

    await waitFor(() => {
      expect(apiMocks.removeOllamaModel).toHaveBeenCalledWith(
        expect.objectContaining({ userId: "admin-1", deviceAuthToken: "device-token-1" }),
        "llama3.2:3b",
        "Remove local Ollama model from admin UI."
      );
    });
  });

  it("disables configured Ollama model profiles from the runtime inventory", async () => {
    const user = userEvent.setup();
    const profileDashboard = {
      ...dashboard,
      profiles: [
        ...dashboard.profiles,
        {
          model_profile_id: "local_ollama_mistral",
          provider_id: "local_ollama",
          model_code: "mistral:7b",
          deployment_name: "mistral:7b",
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
          updated_at: "2026-06-27T10:00:00Z",
          deleted_at: null,
          deleted_by_admin_user_id: "",
          deleted_reason: ""
        }
      ]
    };
    apiMocks.fetchAIModelAdminDashboard.mockResolvedValue(profileDashboard);
    apiMocks.fetchOllamaModels.mockResolvedValue({
      ...inventory,
      models: [
        ...inventory.models,
        {
          name: "mistral:7b",
          model: "mistral:7b",
          modified_at: "2026-06-27T12:00:00Z",
          size: 4_000_000_000,
          digest: "sha256:mistral",
          details: {},
          installed: true,
          configured_profile_ids: ["local_ollama_mistral"],
          active_policy_ids: [],
          is_default: false,
          is_running: false,
          removable: false,
          removal_blockers: ["Configured profile local_ollama_mistral is still enabled."]
        }
      ]
    });
    render(<AIModelAdmin />);

    await user.click(await screen.findByRole("button", { name: /adminOllamaTitle/ }));
    const modelRow = screen.getByRole("row", { name: /mistral:7b/ });
    await user.click(within(modelRow).getByRole("button", { name: /adminOllamaDisable/ }));

    await waitFor(() => {
      expect(apiMocks.upsertAIModelProfile).toHaveBeenCalledWith(
        expect.objectContaining({ userId: "admin-1", deviceAuthToken: "device-token-1" }),
        expect.objectContaining({
          model_profile_id: "local_ollama_mistral",
          enabled: false,
          reason: "Disable local Ollama model profile from admin UI."
        })
      );
    });
  });

  it("sets an installed non-default Ollama model as the local default", async () => {
    const user = userEvent.setup();
    render(<AIModelAdmin />);

    await user.click(await screen.findByRole("button", { name: /adminOllamaTitle/ }));
    const modelRow = screen.getByRole("row", { name: /llama3.2:3b/ });
    await user.click(within(modelRow).getByRole("button", { name: /adminOllamaSetDefault/ }));

    await waitFor(() => {
      expect(apiMocks.upsertAIModelProfile).toHaveBeenCalledWith(
        expect.objectContaining({ userId: "admin-1", deviceAuthToken: "device-token-1" }),
        expect.objectContaining({
          provider_id: "local_ollama",
          model_code: "llama3.2:3b",
          deployment_name: "llama3.2:3b",
          enabled: true,
          is_default_for_free: true,
          reason: "Set local Ollama model as default from admin UI."
        })
      );
    });
  });

  it("searches a user and saves a direct model assignment", async () => {
    const user = userEvent.setup();
    render(<AIModelAdmin />);

    await user.click(await screen.findByRole("button", { name: /adminAssignmentTitle/ }));
    await user.type(screen.getByLabelText("adminAssignmentEmailSearch"), "admin@example.com");
    await user.click(screen.getByRole("button", { name: /adminAssignmentSearch/ }));
    await screen.findByText("Admin User (admin@example.com)");
    await user.selectOptions(screen.getByLabelText("adminAssignmentModel"), "azure_foundry_gpt_4o_mini");
    await user.type(screen.getByLabelText("adminReason"), "Assign external model");
    await user.click(screen.getByRole("button", { name: /adminAssignmentSave/ }));

    await waitFor(() => {
      expect(apiMocks.upsertAIModelUserOverride).toHaveBeenCalledWith(
        expect.objectContaining({ userId: "admin-1", deviceAuthToken: "device-token-1" }),
        "admin-1",
        {
          model_profile_id: "azure_foundry_gpt_4o_mini",
          reason: "Assign external model"
        }
      );
    });
  });
});
