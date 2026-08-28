// @vitest-environment jsdom

import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AIModelAdmin from "../pages/AIModelAdmin";
import {
  fetchAdminCaseCatalogCaseTypes,
  fetchAdminCaseCatalogDocumentTemplates,
  fetchCaseWorkflowAssignments,
  fetchFlowPackCatalog,
  fetchRegisteredCaseWorkflowGraphs,
  validateCaseWorkflowAssignment,
  assignCaseWorkflow,
  fetchAIModelAdminDashboard,
  fetchOllamaModels
} from "../api/adminModelClient";

const translate = vi.hoisted(() => (key: string) => key);

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
  patchAIModelCredential: vi.fn(),
  importOllamaModel: vi.fn(),
  setOllamaModelDefault: vi.fn(),
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

describe("AIModelAdmin case catalog", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("shows case types, linked templates, prompts, and controlled workflow management", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAIModelAdminDashboard).mockResolvedValue(dashboard);
    vi.mocked(fetchOllamaModels).mockResolvedValue({ base_url: "http://127.0.0.1:11434", models: [] });
    const assignment = {
      assignment_id: "assignment-1",
      case_type_key: "employment-dispute",
      jurisdiction: "SK",
      graph_key: "legal_document_workflow",
      graph_version: 1,
      flow_key: "sk.employment.claim",
      flow_version: 1,
      is_active: true,
      validation_status: "valid",
      validation_message: "compatible",
      effective_from: "2026-08-26T00:00:00Z",
      effective_to: null,
      created_by: "admin-1",
      created_at: "2026-08-26T00:00:00Z",
      supersedes_assignment_id: null
    };
    vi.mocked(fetchCaseWorkflowAssignments).mockResolvedValue({ items: [assignment] });
    vi.mocked(fetchFlowPackCatalog).mockResolvedValue({
      items: [{
        flow_key: "sk.employment.claim",
        version: 1,
        jurisdiction: "SK",
        title: "Employment claim",
        description: "Validated flow",
        definition: {},
        is_enabled: true,
        lifecycle_state: "published",
        is_deleted: false,
        created_at: "2026-08-26T00:00:00Z",
        updated_at: "2026-08-26T00:00:00Z"
      }]
    });
    vi.mocked(fetchRegisteredCaseWorkflowGraphs).mockResolvedValue([{
      graph_key: "legal_document_workflow",
      graph_version: 1,
      node_names: ["verify_input", "review_case"],
      supports_interrupt_resume: true,
      supports_automated_finalization: true
    }]);
    vi.mocked(validateCaseWorkflowAssignment).mockResolvedValue({ status: "valid", message: "compatible" });
    vi.mocked(assignCaseWorkflow).mockResolvedValue(assignment);
    vi.mocked(fetchAdminCaseCatalogDocumentTemplates).mockResolvedValue({
      items: [
        {
          template_id: "template-1",
          template_key: "employment-claim-template",
          lineage_key: "employment-claim|claim|sk|sk",
          jurisdiction: "SK",
          language: "sk",
          category: "Employment",
          title: "Employment claim",
          template_kind: "claim",
          description: "Template for employment claims.",
          source_format: "html",
          source_url: "https://example.test/templates/employment-claim",
          body: "",
          keywords: ["employment", "claim"],
          flow_keys: [],
          placeholders: ["employee_name"],
          source_refs: [],
          disclaimer_title: "",
          disclaimer_text: "",
          disclaimer_footer: "",
          is_enabled: true,
          is_deleted: false,
          version: 2,
          latest_version: 2,
          stored_at: "2026-08-18T09:00:00Z",
          newer_version_available: false,
          is_latest_version: true,
          created_at: "2026-08-17T08:00:00Z",
          updated_at: "2026-08-17T08:00:00Z",
          deleted_at: null
        }
      ]
    });
    vi.mocked(fetchAdminCaseCatalogCaseTypes).mockResolvedValue({
      items: [
        {
          case_type_id: "case-type-1",
          case_type_key: "employment-dispute",
          jurisdiction: "SK",
          language: "sk",
          name: "Employment dispute",
          description: "Employment dispute intake.",
          keywords: ["employment", "dispute"],
          is_enabled: true,
          is_deleted: false,
          created_at: "2026-08-17T08:00:00Z",
          updated_at: "2026-08-17T08:00:00Z",
          deleted_at: null,
          prompt: {
            case_prompt_id: "prompt-1",
            prompt_text: "Collect the employment timeline, contract, and termination facts before drafting.",
            created_at: "2026-08-17T08:00:00Z",
            updated_at: "2026-08-17T08:00:00Z"
          },
          templates: [
            {
              template_id: "template-1",
              template_key: "employment-claim-template",
              lineage_key: "employment-claim|claim|sk|sk",
              jurisdiction: "SK",
              language: "sk",
              category: "Employment",
              title: "Employment claim",
              template_kind: "claim",
              description: "Template for employment claims.",
              source_format: "html",
              source_url: "https://example.test/templates/employment-claim",
              body: "",
              keywords: ["employment", "claim"],
              flow_keys: [],
              placeholders: ["employee_name"],
              source_refs: [],
              disclaimer_title: "",
              disclaimer_text: "",
              disclaimer_footer: "",
              is_enabled: true,
              is_deleted: false,
              version: 2,
              latest_version: 2,
              stored_at: "2026-08-18T09:00:00Z",
              newer_version_available: false,
              is_latest_version: true,
              created_at: "2026-08-17T08:00:00Z",
              updated_at: "2026-08-17T08:00:00Z",
              deleted_at: null
            }
          ]
        },
        {
          case_type_id: "case-type-2",
          case_type_key: "general-consultation",
          jurisdiction: "CZ",
          language: "cs",
          name: "General consultation",
          description: "General legal consultation.",
          keywords: ["consultation"],
          is_enabled: false,
          is_deleted: false,
          created_at: "2026-08-17T08:00:00Z",
          updated_at: "2026-08-17T08:00:00Z",
          deleted_at: null,
          prompt: null,
          templates: []
        }
      ]
    });

    render(<AIModelAdmin />);

    await user.click(await screen.findByRole("button", { name: /adminCaseCatalogTitle/ }));

    await waitFor(() => {
      expect(fetchAdminCaseCatalogCaseTypes).toHaveBeenCalledWith(
        expect.objectContaining({ userId: "admin-1", deviceAuthToken: "token-1" })
      );
      expect(fetchAdminCaseCatalogDocumentTemplates).toHaveBeenCalledWith(
        expect.objectContaining({ userId: "admin-1", deviceAuthToken: "token-1" })
      );
    });

    expect(await screen.findAllByText("Employment dispute")).toHaveLength(2);
    expect(screen.getByText("General consultation")).toBeDefined();
    expect(screen.getByText("adminCaseCatalogNoLinkedTemplates")).toBeDefined();
    expect(screen.getByText("adminCaseCatalogPromptMissing")).toBeDefined();
    expect(screen.getByText("legal_document_workflow@1 / sk.employment.claim@1")).toBeDefined();

    await user.click(screen.getAllByRole("button", { name: "adminEdit" })[0]!);
    await user.click(screen.getByRole("checkbox", { name: /Confirm prospective replacement/i }));
    await user.click(screen.getByRole("button", { name: "Validate compatibility" }));
    await waitFor(() => expect(validateCaseWorkflowAssignment).toHaveBeenCalled());
    await user.click(screen.getByRole("button", { name: "Assign for new cases" }));
    await waitFor(() => expect(assignCaseWorkflow).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ confirmation: true, flow_key: "sk.employment.claim" })
    ));

    await user.click(screen.getByRole("button", { name: "adminCaseCatalogTemplatesTitle" }));
    expect(screen.getByText("Employment claim")).toBeDefined();
    expect(screen.getByText("v2")).toBeDefined();

    await user.click(screen.getByRole("button", { name: "adminCaseCatalogPromptsTitle" }));
    const promptDetails = screen.getByText("adminCaseCatalogViewPrompt").closest("details");
    expect(promptDetails).not.toBeNull();
    expect(within(promptDetails as HTMLDetailsElement).getByText(/Collect the employment timeline/)).toBeDefined();
  });
});
