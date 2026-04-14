// @vitest-environment jsdom

import React from "react";
import { describe, expect, it, beforeEach, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CaseProvider, useCases } from "../state/CaseProvider";

vi.mock("../api/chatClient", () => ({
  createChatSession: vi.fn(),
  replyToSession: vi.fn()
}));

vi.mock("../logging/consoleLogger", () => ({
  consoleLogger: {
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn()
  }
}));

const STORAGE_KEY = "aijurisdictionfrontend.mock.cases.v1";

const CaseConsumer: React.FC = () => {
  const { cases, documents, createCase } = useCases();

  return (
    <div>
      <button
        type="button"
        onClick={() =>
          createCase({
            title: "Mock intake",
            jurisdiction: "Slovakia",
            opposingParty: "Northwind LLC",
            documents: [
              {
                originalFilename: "northwind-evidence.pdf",
                mimeType: "application/pdf",
                size: 4096
              }
            ]
          })
        }
      >
        Create
      </button>
      <div data-testid="case-count">{cases.length}</div>
      <div data-testid="document-count">{documents.length}</div>
      <div data-testid="latest-case">{cases[0]?.title ?? ""}</div>
      <div data-testid="latest-document">{documents[0]?.originalFilename ?? ""}</div>
    </div>
  );
};

describe("CaseProvider", () => {
  beforeEach(() => {
    cleanup();
    window.localStorage.clear();
  });

  it("stores created mock cases and aggregated documents in localStorage", async () => {
    const user = userEvent.setup();
    render(
      <CaseProvider>
        <CaseConsumer />
      </CaseProvider>
    );

    const initialCases = Number(screen.getByTestId("case-count").textContent ?? "0");
    const initialDocuments = Number(screen.getByTestId("document-count").textContent ?? "0");

    await user.click(screen.getByRole("button", { name: "Create" }));

    expect(Number(screen.getByTestId("case-count").textContent ?? "0")).toBe(initialCases + 1);
    expect(Number(screen.getByTestId("document-count").textContent ?? "0")).toBe(initialDocuments + 1);
    expect(screen.getByTestId("latest-case").textContent).toBe("Mock intake");
    expect(screen.getByTestId("latest-document").textContent).toBe("northwind-evidence.pdf");

    const rawStoredCases = window.localStorage.getItem(STORAGE_KEY);
    expect(rawStoredCases).not.toBeNull();
    expect(rawStoredCases).toContain("Mock intake");
    expect(rawStoredCases).toContain("northwind-evidence.pdf");
  });

  it("hydrates saved mock cases from localStorage on a fresh mount", () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([
        {
          id: "case-stored",
          title: "Stored case",
          description: "Stored mock case",
          status: "In progress",
          createdAt: "2026-04-14T10:00:00.000Z",
          interactionHistory: [],
          selectedRole: "AI Lawyer",
          selectedMode: "Draft",
          selectedCommunicationMode: "Chat",
          workspace: {
            meta: "Mock",
            objective: "Restore from storage",
            nextAction: "Open the workspace",
            jurisdiction: "Slovakia",
            output: "Brief"
          },
          jurisdiction: "Slovakia",
          opposingParty: "Stored opponent",
          documents: [
            {
              id: "doc-stored",
              caseId: "case-stored",
              originalFilename: "stored-evidence.pdf",
              mimeType: "application/pdf",
              size: 1200,
              sizeLabel: "2 KB",
              uploadedAt: "2026-04-14T10:00:00.000Z"
            }
          ],
          source: "mock"
        }
      ])
    );

    render(
      <CaseProvider>
        <CaseConsumer />
      </CaseProvider>
    );

    expect(screen.getByTestId("case-count").textContent).toBe("1");
    expect(screen.getByTestId("document-count").textContent).toBe("1");
    expect(screen.getByTestId("latest-case").textContent).toBe("Stored case");
    expect(screen.getByTestId("latest-document").textContent).toBe("stored-evidence.pdf");
  });
});
