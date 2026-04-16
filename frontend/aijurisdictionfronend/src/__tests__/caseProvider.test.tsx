// @vitest-environment jsdom

import React from "react";
import { describe, expect, it, beforeEach, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createChatSession, replyToSession } from "../api/chatClient";
import { LanguageProvider, useLanguage } from "../components/LanguageProvider";
import {
  buildLocalizedInteractionMessage,
  CaseProvider,
  useCases
} from "../state/CaseProvider";

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
  const { cases, documents, createCase, activeCase, hasSelectedCase } = useCases();

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
      <div data-testid="active-case">{activeCase?.title ?? ""}</div>
      <div data-testid="has-selected-case">{String(hasSelectedCase)}</div>
    </div>
  );
};

const LocalizedCaseConsumer: React.FC = () => {
  const { cases } = useCases();
  const { setLanguage } = useLanguage();

  return (
    <div>
      <button type="button" onClick={() => setLanguage("sk")}>
        Switch to SK
      </button>
      <div data-testid="localized-title">{cases[0]?.title ?? ""}</div>
      <div data-testid="localized-next-action">{cases[0]?.workspace.nextAction ?? ""}</div>
    </div>
  );
};

const SessionLanguageConsumer: React.FC = () => {
  const { sendCaseMessage } = useCases();
  const { setLanguage } = useLanguage();

  return (
    <div>
      <button
        type="button"
        onClick={() =>
          void sendCaseMessage({
            caseId: "case-001",
            content: "hello",
            communicationMode: "Chat"
          })
        }
      >
        Send EN
      </button>
      <button type="button" onClick={() => setLanguage("sk")}>
        Switch to SK
      </button>
      <button
        type="button"
        onClick={() =>
          void sendCaseMessage({
            caseId: "case-001",
            content: "ahoj",
            communicationMode: "Chat"
          })
        }
      >
        Send SK
      </button>
    </div>
  );
};

const LocalizedSystemMessageConsumer: React.FC = () => {
  const { cases, addInteraction } = useCases();
  const { setLanguage } = useLanguage();

  return (
    <div>
      <button
        type="button"
        onClick={() =>
          addInteraction(
            "case-001",
            "System",
            buildLocalizedInteractionMessage("workspaceApiUnavailablePrefix", {
              detail: "Network request failed."
            })
          )
        }
      >
        Add Error
      </button>
      <button type="button" onClick={() => setLanguage("de")}>
        Switch to DE
      </button>
      <div data-testid="localized-system-message">
        {cases[0]?.interactionHistory.at(-1)?.message ?? ""}
      </div>
    </div>
  );
};

const FirstUserMessageConsumer: React.FC = () => {
  const { cases, addInteraction } = useCases();
  const activeCase = cases.find((caseItem) => caseItem.id === "case-001");

  return (
    <div>
      <button
        type="button"
        onClick={() => addInteraction("case-001", "You", "Please review the first issue.")}
      >
        Send first user message
      </button>
      <div data-testid="case-001-history-actors">
        {activeCase?.interactionHistory.map((interaction) => interaction.actor).join("|") ?? ""}
      </div>
      <div data-testid="case-001-history-messages">
        {activeCase?.interactionHistory.map((interaction) => interaction.message).join("|") ?? ""}
      </div>
    </div>
  );
};

describe("CaseProvider", () => {
  beforeEach(() => {
    cleanup();
    window.localStorage.clear();
    vi.mocked(createChatSession).mockReset();
    vi.mocked(replyToSession).mockReset();
  });

  it("stores created mock cases and aggregated documents in localStorage", async () => {
    const user = userEvent.setup();
    render(
      <LanguageProvider>
        <CaseProvider>
          <CaseConsumer />
        </CaseProvider>
      </LanguageProvider>
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
      <LanguageProvider>
        <CaseProvider>
          <CaseConsumer />
        </CaseProvider>
      </LanguageProvider>
    );

    expect(screen.getByTestId("case-count").textContent).toBe("1");
    expect(screen.getByTestId("document-count").textContent).toBe("1");
    expect(screen.getByTestId("latest-case").textContent).toBe("Stored case");
    expect(screen.getByTestId("latest-document").textContent).toBe("stored-evidence.pdf");
    expect(screen.getByTestId("active-case").textContent).toBe("");
    expect(screen.getByTestId("has-selected-case").textContent).toBe("false");
  });

  it("re-localizes seeded mock case content when the language changes", async () => {
    const user = userEvent.setup();

    render(
      <LanguageProvider>
        <CaseProvider>
          <LocalizedCaseConsumer />
        </CaseProvider>
      </LanguageProvider>
    );

    expect(screen.getByTestId("localized-title").textContent).toBe("Keystone Holdings Intake");

    await user.click(screen.getByRole("button", { name: "Switch to SK" }));

    expect(screen.getByTestId("localized-title").textContent).toBe("Intake Keystone Holdings");
    expect(screen.getByTestId("localized-next-action").textContent).toContain("Naplánujte");
  });

  it("creates a new API session for a case after the language changes", async () => {
    const user = userEvent.setup();
    vi.mocked(createChatSession)
      .mockResolvedValueOnce({
        id: "session-en",
        user_id: null,
        case_id: null,
        country: "SK",
        language: "en",
        discussion_type: "advice",
        state: "active",
        created_at: "2026-04-14T10:00:00.000Z"
      })
      .mockResolvedValueOnce({
        id: "session-sk",
        user_id: null,
        case_id: null,
        country: "SK",
        language: "sk",
        discussion_type: "advice",
        state: "active",
        created_at: "2026-04-14T10:05:00.000Z"
      });
    vi.mocked(replyToSession).mockResolvedValue({
      id: "message-1",
      session_id: "session-en",
      role: "assistant",
      content: "Reply",
      agent_name: "AI Assistant",
      created_at: "2026-04-14T10:00:01.000Z"
    });

    render(
      <LanguageProvider>
        <CaseProvider>
          <SessionLanguageConsumer />
        </CaseProvider>
      </LanguageProvider>
    );

    await user.click(screen.getByRole("button", { name: "Send EN" }));
    await user.click(screen.getByRole("button", { name: "Switch to SK" }));
    await user.click(screen.getByRole("button", { name: "Send SK" }));

    expect(createChatSession).toHaveBeenNthCalledWith(1, { language: "en" });
    expect(createChatSession).toHaveBeenNthCalledWith(2, { language: "sk" });
  });

  it("re-localizes stored system interaction messages after language changes", async () => {
    const user = userEvent.setup();

    render(
      <LanguageProvider>
        <CaseProvider>
          <LocalizedSystemMessageConsumer />
        </CaseProvider>
      </LanguageProvider>
    );

    await user.click(screen.getByRole("button", { name: "Add Error" }));

    expect(screen.getByTestId("localized-system-message").textContent).toBe(
      "Unable to reach API. Network request failed."
    );

    await user.click(screen.getByRole("button", { name: "Switch to DE" }));

    expect(screen.getByTestId("localized-system-message").textContent).toBe(
      "API ist nicht erreichbar. Network request failed."
    );
  });

  it("removes the seeded assistant intro after the first user message is added", async () => {
    const user = userEvent.setup();

    render(
      <LanguageProvider>
        <CaseProvider>
          <FirstUserMessageConsumer />
        </CaseProvider>
      </LanguageProvider>
    );

    expect(screen.getByTestId("case-001-history-actors").textContent).toContain("AI Lawyer");
    expect(screen.getByTestId("case-001-history-messages").textContent).toContain(
      "Opened new case workspace from the intake form."
    );

    await user.click(screen.getByRole("button", { name: "Send first user message" }));

    expect(screen.getByTestId("case-001-history-actors").textContent).not.toContain("AI Lawyer");
    expect(screen.getByTestId("case-001-history-actors").textContent).toContain("System");
    expect(screen.getByTestId("case-001-history-actors").textContent).toContain("You");
    expect(screen.getByTestId("case-001-history-messages").textContent).not.toContain(
      "Opened new case workspace from the intake form."
    );
    expect(screen.getByTestId("case-001-history-messages").textContent).toContain(
      "Please review the first issue."
    );
  });
});
