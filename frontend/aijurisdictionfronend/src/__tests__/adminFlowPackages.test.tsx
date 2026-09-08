// @vitest-environment jsdom

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import {
  createDraftFlowPackVersion,
  createFlowEvaluationRun,
  createFlowEvaluationSuite,
  fetchFlowPackCatalog,
  lockFlowPackVersionForTesting,
  updateDraftFlowPackVersion
} from "../api/adminModelClient";
import AdminFlowPackages from "../pages/AdminFlowPackages";

vi.mock("../components/LanguageProvider", () => ({
  useLanguage: () => ({ t: (key: string) => key })
}));

vi.mock("../api/adminModelClient", () => ({
  fetchFlowPackCatalog: vi.fn(),
  createDraftFlowPackVersion: vi.fn(),
  updateDraftFlowPackVersion: vi.fn(),
  lockFlowPackVersionForTesting: vi.fn(),
  createFlowEvaluationSuite: vi.fn(),
  fetchFlowEvaluationSuite: vi.fn(),
  createFlowEvaluationRun: vi.fn()
}));

const adminAuth = { userId: "admin-1", deviceId: "device-1", deviceAuthToken: "token-1" };
const graph = {
  graph_key: "urbanism_graph",
  graph_version: 2,
  node_names: ["classify", "review"],
  supports_interrupt_resume: true,
  supports_automated_finalization: false
};
const draftFlow = {
  flow_id: "flow-1",
  flow_key: "sk.urbanism.general",
  version: 2,
  jurisdiction: "SK",
  domain: "administrative",
  title: "Urban planning",
  description: "Answers general synthetic urban-planning questions.",
  definition: { graph: "urbanism_graph" },
  question_kind: "general_legal_question",
  legal_domain: "urbanism",
  requested_outcome: "legal_information",
  positive_examples: ["Can a synthetic resident build a garage?"],
  negative_examples: ["Prepare a sale contract"],
  clarification_policy: { on_low_confidence: "ask_user" },
  definition_hash: null,
  locked_at: null,
  locked_by: null,
  locked_reason: null,
  is_enabled: false,
  lifecycle_state: "draft" as const,
  is_deleted: false,
  created_at: "2026-09-08T00:00:00Z",
  updated_at: "2026-09-08T00:00:00Z"
};
const lockedFlow = {
  ...draftFlow,
  definition_hash: "a".repeat(64),
  locked_at: "2026-09-08T01:00:00Z",
  locked_by: "admin-1",
  locked_reason: "Ready for synthetic test",
  lifecycle_state: "test_ready" as const
};

describe("AdminFlowPackages", () => {
  beforeEach(() => {
    vi.mocked(fetchFlowPackCatalog).mockResolvedValue({ items: [draftFlow] });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("validates, saves, locks, and makes an immutable version read-only", async () => {
    const user = userEvent.setup();
    vi.mocked(updateDraftFlowPackVersion).mockResolvedValue({ ...draftFlow, title: "Updated urban planning" });
    vi.mocked(lockFlowPackVersionForTesting).mockResolvedValue(lockedFlow);
    const onStatus = vi.fn();
    render(<AdminFlowPackages adminAuth={adminAuth} graphs={[graph]} onStatus={onStatus} onError={vi.fn()} />);

    expect(await screen.findByDisplayValue("Urban planning")).toBeDefined();
    await user.selectOptions(screen.getByLabelText("adminFlowRegisteredGraph"), "urbanism_graph@2");
    const title = screen.getByLabelText("adminFlowTitle");
    await user.clear(title);
    await user.type(title, "Updated urban planning");
    await user.click(screen.getByRole("button", { name: "adminFlowValidate" }));
    expect(screen.getByText("adminFlowValidationPassed")).toBeDefined();
    await user.click(screen.getByRole("button", { name: "adminFlowSaveDraft" }));
    await waitFor(() => expect(updateDraftFlowPackVersion).toHaveBeenCalledWith(
      adminAuth,
      "sk.urbanism.general",
      2,
      "SK",
      expect.objectContaining({ title: "Updated urban planning", legal_domain: "urbanism" })
    ));

    await user.type(screen.getByLabelText("adminReason"), "Ready for synthetic test");
    await user.click(screen.getByRole("button", { name: "adminFlowLockTesting" }));
    await waitFor(() => expect(lockFlowPackVersionForTesting).toHaveBeenCalled());
    expect(await screen.findByText("adminFlowImmutableNotice")).toBeDefined();
    expect(screen.getByLabelText("adminFlowTitle")).toHaveProperty("disabled", true);
    expect(onStatus).toHaveBeenCalledWith("adminFlowLocked");
  });

  it("creates a confirmed synthetic suite and shows passing evaluation gates", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchFlowPackCatalog).mockResolvedValue({ items: [lockedFlow] });
    vi.mocked(createFlowEvaluationSuite).mockResolvedValue({
      suite_id: "suite-1", suite_key: "urbanism-suite", version: 1, jurisdiction: "SK",
      title: "Urbanism suite", synthetic_only: true, routing_accuracy_threshold: 1,
      retention_days: 7, suite_hash: "b".repeat(64), case_count: 1,
      created_by: "admin-1", created_at: "2026-09-08T01:00:00Z"
    });
    vi.mocked(createFlowEvaluationRun).mockResolvedValue({
      run_id: "run-1", idempotency_key: "admin-ui-id", synthetic_run_id: "synthetic-id",
      suite_id: "suite-1", suite_key: "urbanism-suite", suite_version: 1,
      suite_hash: "b".repeat(64), flow_id: "flow-1", flow_key: lockedFlow.flow_key,
      flow_version: 2, flow_definition_hash: "a".repeat(64), graph_version: "urbanism_graph@2",
      routing_policy_hash: "c".repeat(64), provider: "azurefoundry", model: "gpt-test",
      provider_route: "offline-admin-evaluation", mode: "routing_only", status: "passed",
      metrics: { routing_accuracy: 1 }, gates: { routing_threshold: true, privacy: true, human_review: true },
      created_by: "admin-1", created_at: "2026-09-08T01:00:00Z", expires_at: "2026-09-15T01:00:00Z"
    });
    render(<AdminFlowPackages adminAuth={adminAuth} graphs={[graph]} onStatus={vi.fn()} onError={vi.fn()} />);

    expect(await screen.findByText("adminFlowSuiteTitle")).toBeDefined();
    await user.selectOptions(screen.getByLabelText("adminFlowRegisteredGraph"), "urbanism_graph@2");
    await user.click(screen.getAllByText("adminFlowCreateSuite")[0]!);
    await user.type(screen.getByLabelText("adminFlowSuiteKey"), "urbanism-suite");
    await user.type(screen.getByLabelText("adminFlowSuiteName"), "Urbanism suite");
    await user.click(screen.getByLabelText("adminFlowSyntheticConfirm"));
    await user.click(screen.getByRole("button", { name: "adminFlowCreateSuite" }));
    await waitFor(() => expect(createFlowEvaluationSuite).toHaveBeenCalledWith(
      adminAuth,
      expect.objectContaining({ synthetic_only: true, synthetic_data_confirmed: true })
    ));

    await user.type(screen.getByLabelText("adminFlowModel"), "gpt-test");
    await user.click(screen.getByLabelText("adminFlowHumanReview"));
    await user.click(screen.getByRole("button", { name: "adminFlowRun" }));
    await waitFor(() => expect(createFlowEvaluationRun).toHaveBeenCalled());
    expect(await screen.findByText("adminFlowRunPassed")).toBeDefined();
    expect(screen.getByText("✓ privacy")).toBeDefined();
  });

  it("clones locked content instead of editing it in place", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchFlowPackCatalog).mockResolvedValue({ items: [lockedFlow] });
    vi.mocked(createDraftFlowPackVersion).mockResolvedValue({ ...draftFlow, version: 3 });
    render(<AdminFlowPackages adminAuth={adminAuth} graphs={[graph]} onStatus={vi.fn()} onError={vi.fn()} />);
    await user.click(await screen.findByRole("button", { name: "adminFlowCloneDraft" }));
    await waitFor(() => expect(createDraftFlowPackVersion).toHaveBeenCalledWith(
      adminAuth, lockedFlow.flow_key, "SK"
    ));
    expect(await screen.findByDisplayValue("Urban planning")).toHaveProperty("disabled", false);
  });
});
