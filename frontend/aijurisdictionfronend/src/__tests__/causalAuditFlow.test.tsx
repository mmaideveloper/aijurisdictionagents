// @vitest-environment jsdom
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CausalAuditFlow } from "../components/CausalAuditFlow";

describe("causal audit flow", () => {
  it("shows only recorded parents, preserves retries and exposes gaps", () => {
    render(<CausalAuditFlow t={(key) => key} flow={{
      nodes: [{ id: "root", label: "API" }, { id: "first", label: "Model attempt 1" },
        { id: "second", label: "Model attempt 2" }, { id: "other", label: "Unrelated turn" }],
      edges: [{ from: "root", to: "first" }, { from: "root", to: "second" }],
      evidence_gaps: ["parent_not_recorded"]
    }} />);
    expect(screen.getByRole("status").textContent).toContain("parent_not_recorded");
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(4);
    expect(within(items[1]!).getByText(/adminCausalParent/).textContent).toContain("API");
    expect(within(items[2]!).getByText(/adminCausalParent/).textContent).toContain("API");
    expect(within(items[3]!).queryByText(/adminCausalParent/)).toBeNull();
  });
});
