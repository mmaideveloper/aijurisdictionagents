// @vitest-environment jsdom
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { LangGraphAuditGraph } from "../components/LangGraphAuditGraph";
import type { AdminLangGraphEvidence } from "../api/adminModelClient";

afterEach(cleanup);
it("does not describe a missing graph run as historical or unexecuted", () => {
  const evidence: AdminLangGraphEvidence = {
    schema_version: 1, runs: [], completeness: "complete",
    page: { limit: 100, offset: 0, returned_events: 0, next_offset: null, has_more: false },
  };
  render(<LangGraphAuditGraph evidence={evidence} t={key => key} />);
  expect(screen.getByRole("status").textContent).toBe("adminDebugNoGraphEvidence");
  expect(screen.queryByText("adminDebugGraphUnavailable")).toBeNull();
});

it("keeps the historical warning for a recorded run whose topology is missing", () => {
  const evidence: AdminLangGraphEvidence = {
    schema_version: 1, completeness: "partial",
    page: { limit: 100, offset: 0, returned_events: 0, next_offset: null, has_more: false },
    runs: [{
      workflow_run_id: "historical", parent_run_id: "", session_id: "s", turn_id: "",
      graph_key: "old_graph", graph_version: 1, flow_key: "", flow_version: 0,
      run_status: "completed", current_node_id: "", topology_status: "unavailable",
      topology: null, topology_digest: "", occurrences: [], observed_transition_ids: [],
      evidence_completeness: "partial", evidence_gaps: [], unmapped_event_count: 0,
      created_at: "", updated_at: "",
    }],
  };
  render(<LangGraphAuditGraph evidence={evidence} t={key => key} />);
  expect(screen.getByRole("status").textContent).toBe("adminDebugGraphUnavailable");
  expect(screen.getByText("adminProviderSummaryUnavailable")).toBeTruthy();
  expect(screen.queryByText("adminDebugNoGraphEvidence")).toBeNull();
  expect(screen.queryByText("@0")).toBeNull();
});
