// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import type { AdminDebugTrace } from "../api/adminModelClient";
import { ResponseScoreEvidence } from "../components/ResponseScoreEvidence";

afterEach(cleanup);
it.each(["incomplete", "blocked"] as const)("never renders a numeric score for %s", status => {
  const trace = { response_score_evidence: { assessments: [{ assessment_id: "a", answer_revision: "answer-1", policy_version: "1", status, score: "100", requires_human_review: true, missing_evidence: ["gate:grounding"] }] } } as AdminDebugTrace;
  render(<ResponseScoreEvidence trace={trace} language="en" />);
  expect(screen.queryByText(/100/)).toBeNull();
  expect(screen.getByText("answer-1")).toBeTruthy();
  expect(screen.getByText("Human review required")).toBeTruthy();
});
it("keeps historical absence explicit", () => {
  render(<ResponseScoreEvidence trace={{} as AdminDebugTrace} language="en" />);
  expect(screen.getByText("No assessment recorded")).toBeTruthy();
});
