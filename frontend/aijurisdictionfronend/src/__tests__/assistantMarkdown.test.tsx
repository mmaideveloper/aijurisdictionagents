// @vitest-environment jsdom
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AssistantDocumentLinkContext, AssistantMarkdown } from "../components/AssistantMarkdown";
import { isUserDocument } from "../utils/assistantPresentation";

afterEach(cleanup);

describe("legal explanation presentation", () => {
  it("preserves question headings, emphasis, lists, tables and citations", () => {
    render(<AssistantMarkdown text={"USER-FACING (Slovak):\n**Prehľad**\n\n### Môže ísť do práce?\n\nPodľa režimu.\n\n- Podmienka\n\n| Činnosť | Podmienky |\n| --- | --- |\n| Obchod | Overiť |\n\n[Zdroj](https://example.org/law)"} />);
    expect(screen.getByRole("heading", { name: "Môže ísť do práce?" })).toBeTruthy();
    expect(document.querySelector("strong")?.textContent).toBe("Prehľad");
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByRole("listitem").textContent).toBe("Podmienka");
    expect(screen.getByRole("link", { name: "Zdroj" }).getAttribute("href")).toBe("https://example.org/law");
    expect(document.body.textContent).not.toContain("USER-FACING");
  });

  it("does not execute raw HTML, load images or link unsafe URLs", () => {
    render(<AssistantMarkdown text={'<script>alert(1)</script>\n\n<img src="https://example.org/pixel">\n\n![pixel](https://example.org/pixel)\n\n[bad](javascript:alert)\n\n[file](file:///secret)\n\n[remote](//example.org)'} />);
    expect(document.querySelector("script, img, iframe")).toBeNull();
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });

  it("excludes technical records by kind without hiding ordinary JSON uploads", () => {
    expect(isUserDocument({ kind: "technical_payload" })).toBe(false);
    expect(isUserDocument({ kind: "uploaded_document" })).toBe(true);
    expect(isUserDocument({ kind: "generated_document" })).toBe(true);
  });
});


describe("generated document links", () => {
  const renderWithPolicy = (text: string, allowed: boolean = false) => {
    const retry = vi.fn();
    render(<AssistantDocumentLinkContext.Provider value={{
      isAllowed: () => allowed, unavailableLabel: "Document not ready", retryLabel: "Retry generation",
      retryDisabled: false, onRetry: retry
    }}><AssistantMarkdown text={text} /></AssistantDocumentLinkContext.Provider>);
    return retry;
  };

  it.each(["#", "/", "/app/assistant#", "https://agent.jurisdigta.eu/app/assistant#"])(
    "blocks a placeholder download target %s without navigating", (href) => {
      const retry = renderWithPolicy(`[Stiahnuť pracovnú zmluvu](${href})`);
      expect(screen.queryAllByRole("link")).toHaveLength(0);
      expect(screen.getByRole("status").textContent).toContain("Document not ready");
      screen.getByRole("button", { name: "Retry generation" }).click();
      expect(retry).toHaveBeenCalledOnce();
    }
  );

  it("checks reference-style links and formatted labels after Markdown parsing", () => {
    renderWithPolicy("[**Stiahnuť pracovnú zmluvu**][pdf]\n\n[pdf]: #");
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(screen.getByRole("status")).toBeTruthy();
  });

  it("keeps verified viewer links and source citations working", () => {
    renderWithPolicy("[Download contract](/app/documents/view?caseId=case&docId=saved)\n\n[Source](https://example.org/law.pdf)\n\n[Section](#section)", true);
    expect(screen.getByRole("link", { name: "Download contract" }).getAttribute("href")).toContain("docId=saved");
    expect(screen.getByRole("link", { name: "Source" }).getAttribute("href")).toBe("https://example.org/law.pdf");
    expect(screen.getByRole("link", { name: "Section" }).getAttribute("href")).toBe("#section");
  });

  it("fails closed for document actions outside a case context", () => {
    render(<AssistantMarkdown text="[Download contract](/app/documents/view?caseId=case&docId=invented)" />);
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });
});
