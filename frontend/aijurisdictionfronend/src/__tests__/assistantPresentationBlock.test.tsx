// @vitest-environment jsdom

import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { AssistantPresentationBlock } from "../components/AssistantPresentationBlock";
import { LanguageProvider } from "../components/LanguageProvider";
import type { PresentationBlock } from "../presentation";

afterEach(cleanup);

const renderBlock = (block: PresentationBlock) => render(
  <LanguageProvider><AssistantPresentationBlock block={block} /></LanguageProvider>
);

describe("AssistantPresentationBlock", () => {
  it("renders structured records as a semantic table with visible provenance", () => {
    renderBlock({
      schema_version: 1,
      renderer_id: "data_table",
      renderer_version: 1,
      data: { columns: ["tool_name", "status"], rows: [{ tool_name: "company_check", status: "verified" }] },
      fallback_text: "Company check completed.",
      citations: ["synthetic-source-755"],
      notices: ["Human review is required before legal use."],
      selection: {
        policy_id: "test.presentation.v1",
        reason_code: "model_proposal_validated",
        explicit_user_request: false,
        model_proposal_accepted: true
      }
    });

    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByText("company_check")).toBeTruthy();
    expect(screen.getByText("synthetic-source-755")).toBeTruthy();
    expect(screen.getByText(/Human review/)).toBeTruthy();
  });

  it("renders JSON as escaped text rather than executable markup", () => {
    const malicious = '<img src=x onerror="window.__unsafe=true">';
    const { container } = renderBlock({
      schema_version: 1,
      renderer_id: "sanitized_json",
      renderer_version: 1,
      data: { answer: malicious },
      fallback_text: malicious,
      citations: [],
      notices: [],
      selection: {
        policy_id: "test.presentation.v1",
        reason_code: "explicit_user_format",
        explicit_user_request: true,
        model_proposal_accepted: false
      }
    });

    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText(new RegExp("onerror"))).toBeTruthy();
  });
});
