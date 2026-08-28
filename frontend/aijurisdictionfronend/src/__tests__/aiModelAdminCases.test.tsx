// @vitest-environment jsdom

import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AIModelAdmin from "../pages/AIModelAdmin";
import {
  fetchAdminCaseExportBlob,
  fetchAdminUserCases,
  fetchAIModelAdminDashboard,
  fetchOllamaModels,
  searchAdminCaseUsers,
  softDeleteAdminCase
} from "../api/adminModelClient";

const translate = vi.hoisted(() => (key: string, values?: Record<string, string>) => {
  if (key === "adminCasesDeleteConfirm") {
    return `Delete ${values?.title} ${values?.id} ${values?.email}?`;
  }
  return key;
});

vi.mock("../auth/webAuth", () => ({
  useAuth: () => ({
    user: { userId: "admin-1", deviceId: "device-1", deviceAuthToken: "token-1" }
  })
}));

vi.mock("../components/LanguageProvider", () => ({
  useLanguage: () => ({
    t: translate
  })
}));

vi.mock("../api/adminModelClient", () => ({
  fetchAdminUsers: vi.fn(),
  fetchAdminCaseExportBlob: vi.fn(),
  fetchAdminCaseCatalogCaseTypes: vi.fn(),
  fetchAdminCaseCatalogDocumentTemplates: vi.fn(),
  fetchCaseWorkflowAssignments: vi.fn(),
  fetchFlowPackCatalog: vi.fn(),
  fetchRegisteredCaseWorkflowGraphs: vi.fn(),
  validateCaseWorkflowAssignment: vi.fn(),
  assignCaseWorkflow: vi.fn(),
  createDraftFlowPackVersion: vi.fn(),
  fetchAdminUserCases: vi.fn(),
  fetchAIModelAdminDashboard: vi.fn(),
  fetchAIModelUserOverride: vi.fn(),
  fetchOllamaModels: vi.fn(),
  searchAIModelAssignmentUsers: vi.fn(),
  searchAdminCaseUsers: vi.fn(),
  softDeleteAdminCase: vi.fn(),
  deleteAIModelProvider: vi.fn(),
  deleteAIModelProfile: vi.fn(),
  deleteAIModelGroup: vi.fn(),
  deleteAIModelRoutePolicy: vi.fn(),
  upsertAIModelUserOverride: vi.fn(),
  disableAIModelUserOverride: vi.fn(),
  upsertAIModelProvider: vi.fn(),
  upsertAIModelProfile: vi.fn(),
  upsertAIModelGroup: vi.fn(),
  addAIModelGroupMember: vi.fn(),
  upsertAIModelRoutePolicy: vi.fn(),
  upsertAIModelCredential: vi.fn(),
  importOllamaModel: vi.fn(),
  removeOllamaModel: vi.fn(),
  updateAdminUser: vi.fn()
}));

const dashboard = {
  providers: [],
  profiles: [],
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

const targetUser = {
  user_id: "user-1",
  email: "mmatonok@gmail.com",
  full_name: "M Mato",
  role: "user",
  is_enabled: true,
  created_at: "2026-06-29T08:00:00Z"
};

const targetCase = {
  case_id: "case-1",
  user_id: "user-1",
  target_user_email: "mmatonok@gmail.com",
  title: "Expired free case",
  status: "open",
  created_at: "2026-06-27T08:00:00Z",
  updated_at: "2026-06-27T08:00:00Z"
};

describe("AIModelAdmin case reset panel", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("downloads an audited admin case export from each case row", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAIModelAdminDashboard).mockResolvedValue(dashboard);
    vi.mocked(fetchOllamaModels).mockResolvedValue({ base_url: "http://127.0.0.1:11434", models: [] });
    vi.mocked(searchAdminCaseUsers).mockResolvedValue({ items: [targetUser], total: 1, limit: 25 });
    vi.mocked(fetchAdminUserCases).mockResolvedValue({
      user: targetUser,
      cases: [
        targetCase,
        {
          ...targetCase,
          case_id: "case-2",
          title: "Paid validation fixture"
        }
      ]
    });
    vi.mocked(fetchAdminCaseExportBlob).mockResolvedValue({
      blob: new Blob(["zip body"], { type: "application/zip" }),
      contentType: "application/zip",
      filename: "case-export.zip"
    });
    URL.createObjectURL = vi.fn(() => "blob:admin-case-export");
    URL.revokeObjectURL = vi.fn();
    const clickSpy = vi.fn();

    render(<AIModelAdmin />);

    await user.click(await screen.findByRole("button", { name: /adminCasesTitle/ }));
    await user.type(screen.getByLabelText("adminCasesEmailSearch"), "mmatonok@gmail.com");
    await user.click(screen.getByRole("button", { name: /adminCasesSearch/ }));
    await screen.findByText("Expired free case");
    await screen.findByText("Paid validation fixture");

    const exportButtons = await screen.findAllByRole("button", { name: /adminCasesExport/ });
    expect(exportButtons).toHaveLength(2);
    const firstExportButton = exportButtons[0];
    expect(firstExportButton).toBeDefined();
    const appendSpy = vi.spyOn(document.body, "appendChild");
    appendSpy.mockImplementation((node: Node) => {
      if (node instanceof HTMLAnchorElement) {
        node.click = clickSpy;
      }
      return node;
    });
    await user.click(firstExportButton as HTMLElement);

    await waitFor(() => {
      expect(fetchAdminCaseExportBlob).toHaveBeenCalledWith(
        expect.objectContaining({ userId: "admin-1" }),
        "case-1",
        "user-1",
        "adminCasesDefaultReason"
      );
    });
    expect(clickSpy).toHaveBeenCalled();
    expect(await screen.findByText("adminCasesExportSuccess")).not.toBeNull();
  });

  it("searches users, confirms a case soft-delete, and refreshes the case list", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAIModelAdminDashboard).mockResolvedValue(dashboard);
    vi.mocked(fetchOllamaModels).mockResolvedValue({ base_url: "http://127.0.0.1:11434", models: [] });
    vi.mocked(searchAdminCaseUsers).mockResolvedValue({ items: [targetUser], total: 1, limit: 25 });
    vi.mocked(fetchAdminUserCases)
      .mockResolvedValueOnce({ user: targetUser, cases: [targetCase] })
      .mockResolvedValueOnce({ user: targetUser, cases: [{ ...targetCase, status: "deleted" }] });
    vi.mocked(softDeleteAdminCase).mockResolvedValue({
      case: { ...targetCase, status: "deleted" },
      deleted: true
    });
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<AIModelAdmin />);

    await user.click(await screen.findByRole("button", { name: /adminCasesTitle/ }));
    await user.type(screen.getByLabelText("adminCasesEmailSearch"), "mmatonok@gmail.com");
    await user.click(screen.getByRole("button", { name: /adminCasesSearch/ }));
    await screen.findByText(/M Mato/);
    await screen.findByText("Expired free case");
    await user.click(screen.getByRole("button", { name: /adminCasesSoftDelete/ }));

    await waitFor(() => {
      expect(softDeleteAdminCase).toHaveBeenCalledWith(
        expect.objectContaining({ userId: "admin-1" }),
        "case-1",
        "user-1",
        "adminCasesDefaultReason"
      );
    });
    expect(confirmSpy).toHaveBeenCalledWith("Delete Expired free case case-1 mmatonok@gmail.com?");
    expect(fetchAdminUserCases).toHaveBeenCalledTimes(2);
    expect(await screen.findByText("adminCasesDeleteSuccess")).not.toBeNull();
  });
});
