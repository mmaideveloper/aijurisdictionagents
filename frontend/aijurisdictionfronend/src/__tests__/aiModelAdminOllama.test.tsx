// @vitest-environment jsdom

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AIModelAdmin from "../pages/AIModelAdmin";

const apiMocks = vi.hoisted(() => ({
  fetchAIModelAdminDashboard: vi.fn(),
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
      role: "admin"
    }
  })
}));

const translateKey = (key: string) => key;

vi.mock("../components/LanguageProvider", () => ({
  useLanguage: () => ({
    t: translateKey
  })
}));

const dashboard = {
  providers: [],
  profiles: [],
  credentials: [],
  policies: [],
  groups: [],
  memberships: [],
  users: [],
  audit_events: [],
  route_priority: [],
  compliance_notes: [],
  grafana_url: "https://admin.jurisdigta.eu/grafana/"
};

const inventory = {
  base_url: "http://127.0.0.1:11434",
  models: [
    {
      name: "qwen3.6:27b",
      model: "qwen3.6:27b",
      modified_at: "2026-06-27T10:00:00Z",
      size: 17_000_000_000,
      digest: "sha256:default",
      details: {},
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

    expect(await screen.findByText("qwen3.6:27b")).toBeDefined();
    expect(screen.getByText("llama3.2:3b")).toBeDefined();
    expect(screen.getByText("local_ollama_default")).toBeDefined();

    const removeButtons = screen.getAllByRole("button", { name: /adminOllamaRemove/ });
    expect(removeButtons.at(0)?.hasAttribute("disabled")).toBe(true);
  });

  it("starts import and safe remove jobs", async () => {
    const user = userEvent.setup();
    render(<AIModelAdmin />);

    await user.click(await screen.findByRole("button", { name: /adminOllamaTitle/ }));
    await user.type(screen.getByLabelText("adminOllamaModelTag"), "gemma3:4b");
    await user.type(screen.getByLabelText("adminReason"), "Add fallback model");
    await user.click(screen.getByRole("button", { name: /adminOllamaImport/ }));

    await waitFor(() => {
      expect(apiMocks.importOllamaModel).toHaveBeenCalledWith("admin-1", "gemma3:4b", "Add fallback model");
    });

    await user.type(screen.getByLabelText("adminOllamaRemoveReason"), "Remove unused model");
    const removeButtons = screen.getAllByRole("button", { name: /adminOllamaRemove/ });
    const unusedRemoveButton = removeButtons.at(1);
    expect(unusedRemoveButton).toBeDefined();
    await user.click(unusedRemoveButton as HTMLElement);

    await waitFor(() => {
      expect(apiMocks.removeOllamaModel).toHaveBeenCalledWith("admin-1", "llama3.2:3b", "Remove unused model");
    });
  });
});
