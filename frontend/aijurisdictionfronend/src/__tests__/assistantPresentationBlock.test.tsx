// @vitest-environment jsdom

import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AssistantPresentationBlock } from "../components/AssistantPresentationBlock";
import { AssistantDocumentLinkContext } from "../components/AssistantMarkdown";
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

const actionBlock = (href: string, label = "Stiahnuť pracovnú zmluvu"): PresentationBlock => ({
  schema_version: 1, renderer_id: "action_link", renderer_version: 1,
  data: { href, label }, fallback_text: label, citations: [], notices: [],
  selection: { policy_id: "test.v1", reason_code: "validated", explicit_user_request: false, model_proposal_accepted: true }
});

describe("structured document actions", () => {
  const savedHref = "/app/documents/view?caseId=case&docId=saved";
  const withPolicy = (href: string, disabled = false, label?: string) => {
    const retry = vi.fn();
    render(<AssistantDocumentLinkContext.Provider value={{
      isAllowed: (target) => target === savedHref, unavailableLabel: "Document not ready",
      retryLabel: "Retry generation", retryDisabled: disabled, onRetry: retry
    }}><LanguageProvider><AssistantPresentationBlock block={actionBlock(href, label)} /></LanguageProvider></AssistantDocumentLinkContext.Provider>);
    return retry;
  };

  it.each(["#", "/", "/app/assistant#", "https://agent.jurisdigta.eu/app/assistant#",
    "/app/documents/view?caseId=case&docId=missing", "/app/documents/view?caseId=other&docId=saved",
    "/v1/cases/case/documents/saved/pdf", "https://example.test/invented.pdf"])("blocks unverified structured download %s", (href) => {
    const retry = withPolicy(href);
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(screen.getByRole("status").textContent).toContain("Document not ready");
    screen.getByRole("button", { name: "Retry generation" }).click();
    expect(retry).toHaveBeenCalledOnce();
  });

  it("disables retry while generation is running", () => {
    const retry = withPolicy("/app/assistant#", true);
    const button = screen.getByRole("button", { name: "Retry generation" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    button.click();
    expect(retry).not.toHaveBeenCalled();
  });

  it("keeps verified document actions usable", () => {
    withPolicy(savedHref);
    expect(screen.getByRole("link").getAttribute("href")).toBe(savedHref);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("checks viewer targets even with a neutral label", () => {
    withPolicy("/app/documents/view?caseId=case&docId=missing", false, "Open");
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByRole("status")).toBeTruthy();
  });

  it.each(["PDF", "Otvoriť PDF", "Zobraziť dokument", "Open document", "PDF öffnen"])(
    "verifies structured document-opening label %s", (label) => {
      withPolicy("/app/assistant#", false, label);
      expect(screen.queryByRole("link")).toBeNull();
      expect(screen.getByRole("status")).toBeTruthy();
    }
  );

  it("allows the PDF label when the saved viewer target is verified", () => {
    withPolicy(savedHref, false, "PDF");
    expect(screen.getByRole("link", { name: "PDF" }).getAttribute("href")).toBe(savedHref);
  });

  it("fails closed without a case policy", () => {
    renderBlock(actionBlock(savedHref));
    expect(screen.queryByRole("link")).toBeNull();
  });

  it.each(["javascript:alert(1)", "//example.test", "/app/\\evil.test", "/app/assistant\n"])(
    "rejects unsafe structured targets %s", (href) => {
      withPolicy(href, false, "Open");
      expect(screen.queryByRole("link")).toBeNull();
    }
  );

  it("preserves ordinary navigation", () => {
    withPolicy("/app/cases", false, "Open cases");
    expect(screen.getByRole("link", { name: "Open cases" }).getAttribute("href")).toBe("/app/cases");
  });
});
