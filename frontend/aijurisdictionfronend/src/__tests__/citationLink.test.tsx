// @vitest-environment jsdom
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { CitationLink } from "../components/CitationLink";
import type { CaseCitation } from "../state/CaseProvider";

const citation: CaseCitation = {
  id: "citation", caseId: "case", questionMessageId: null, answerMessageId: null,
  sourceType: "law", sourceId: "law-source", sourceUrl: "https://internal-mcp/private",
  title: "Law", citationLabel: "§ 4 zákona č. 190/2003 Z. z.", lawNumber: "190/2003",
  section: "§ 4", effectiveFrom: "2025-07-01", court: null, ecli: null, fileNumber: null,
  decisionDate: null, snippet: null, retrievalTool: null, relevanceScore: null, createdAt: "2026-10-02",
};
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("CitationLink", () => {
  it("opens the authorized law page in a separate tab and removes its opener", () => {
    const replace = vi.fn();
    const tab = { opener: window, location: { replace } };
    vi.spyOn(window, "open").mockReturnValue(tab as unknown as Window);
    render(<CitationLink citation={citation} />);
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("/sources/case/citation");
    expect(link.getAttribute("target")).toBe("_blank");
    fireEvent.click(link);
    expect(tab.opener).toBeNull();
    expect(replace).toHaveBeenCalledWith("/sources/case/citation");
  });

  it("never falls back to an internal law URL when the version is missing", () => {
    render(<CitationLink citation={{ ...citation, effectiveFrom: null }} />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText(citation.citationLabel!)).toBeTruthy();
  });

  it.each(["javascript:alert(1)", "data:text/html,unsafe", "http://insecure.test"])("rejects unsafe external URL %s", sourceUrl => {
    render(<CitationLink citation={{ ...citation, sourceType: "web", sourceUrl }} />);
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("preserves an original HTTPS web source", () => {
    render(<CitationLink citation={{ ...citation, sourceType: "web", sourceUrl: "https://www.slov-lex.sk/" }} />);
    expect(screen.getByRole("link").getAttribute("href")).toBe("https://www.slov-lex.sk/");
  });
});
