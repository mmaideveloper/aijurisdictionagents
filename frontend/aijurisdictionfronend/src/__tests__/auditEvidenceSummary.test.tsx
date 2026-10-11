// @vitest-environment jsdom
import { fireEvent, render, screen, cleanup, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AuditEvidenceSummary } from "../components/AuditEvidenceSummary";
import { fetchAdminDebugTrace, type AdminDebugTrace } from "../api/adminModelClient";

vi.mock("../api/adminModelClient", () => ({ fetchAdminDebugTrace: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const trace = { correlation_id: "synthetic", warnings: ["unavailable"], langgraph_evidence: { runs: [], completeness: "partial", page: { offset: 0, limit: 10, has_more: true, next_offset: 10 } } } as unknown as AdminDebugTrace;

it("keeps missing evidence unknown, shows remote outage and accessible pagination", async () => {
  vi.mocked(fetchAdminDebugTrace).mockResolvedValue(trace);
  const onGraphPage = vi.fn();
  render(<AuditEvidenceSummary trace={trace} language="en" adminAuth={{ userId: "synthetic" }} onGraphPage={onGraphPage} />);
  expect(screen.queryByText("Passed")).toBeNull();
  expect(screen.getAllByText("Not recorded / unknown")).toHaveLength(6);
  expect(screen.getByText(/retained local records remain visible/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Next graph evidence page" }));
  await waitFor(() => expect(onGraphPage).toHaveBeenCalledWith("synthetic", trace.langgraph_evidence));
  expect(fetchAdminDebugTrace).toHaveBeenCalledWith({ userId: "synthetic" }, "synthetic", 10);
});

it("renders malicious labels as text and keeps failed checks distinct from coverage", () => {
  const evidence = { ...trace, validation_evidence: { categories: [{ category: "output_quality", evidence_status: "recorded" }], checks: [{ execution_id: "one", validator_id: "<script>alert(1)</script>", category: "output_quality", outcome: "failed", validator_version: null, artifact_link_status: "missing_evidence" }] } };
  const { container } = render(<AuditEvidenceSummary trace={evidence} language="en" adminAuth={{ userId: "synthetic" }} onGraphPage={vi.fn()} />);
  expect(screen.getByText("Failed")).toBeTruthy();
  expect(screen.getByText("Recorded")).toBeTruthy();
  expect(container.querySelector("script")).toBeNull();
  expect(screen.getByText("<script>alert(1)</script>")).toBeTruthy();
});

it.each(["sk", "de"] as const)("localizes evidence absence in %s", language => {
  render(<AuditEvidenceSummary trace={trace} language={language} adminAuth={{ userId: "synthetic" }} onGraphPage={vi.fn()} />);
  expect(screen.queryByText("Not recorded / unknown")).toBeNull();
  expect(screen.getByRole("button")).toBeTruthy();
});
