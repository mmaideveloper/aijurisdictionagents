// @vitest-environment jsdom

import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Sidebar, buildChatPreview } from "../components/Sidebar";

const navigate = vi.fn();
const selectCase = vi.fn();
const setCaseCommunicationMode = vi.fn();

vi.mock("react-router-dom", () => ({
  useNavigate: () => navigate
}));

vi.mock("../auth/webAuth", () => ({
  useAuth: () => ({
    user: { userId: "user-1" }
  })
}));

vi.mock("../components/LanguageProvider", () => ({
  useLanguage: () => ({
    t: (key: string) =>
      ({
        appName: "AIJurisdiction",
        tagline: "Legal AI",
        sidebarCasesTitle: "Cases",
        sidebarNewCase: "+ New case",
        sidebarCasesEmpty: "No cases.",
        sidebarSelectedCaseTitle: "Selected case",
        sidebarSelectedCaseId: "Case ID",
        sidebarSelectedCaseCreated: "Created",
        sidebarSelectedCaseJurisdiction: "Jurisdiction",
        sidebarSelectedCaseOutput: "Output",
        sidebarSelectedDocuments: "Documents",
        sidebarSelectedDocumentsEmpty: "No documents.",
        sidebarSelectedChats: "Chats",
        sidebarSelectedChatsEmpty: "No chats.",
        sidebarNavigationTitle: "Navigation",
        sidebarComingSoon: "Soon",
        sidebarPlaceholder: "Shortcuts",
        sidebarFooter: "Workspace controls",
        workspaceStatusInProgress: "In progress"
      })[key] ?? key
  })
}));

vi.mock("../state/CaseProvider", () => ({
  useCases: () => ({
    cases: [
      {
        id: "case-1",
        title: "Stored case",
        status: "In progress",
        workspace: { meta: "1 chat" }
      }
    ],
    activeCase: {
      id: "case-1",
      title: "Stored case",
      description: "Case description",
      status: "In progress",
      createdAt: "2026-06-22T09:00:00.000Z",
      workspace: {
        meta: "1 chat",
        jurisdiction: "SK",
        output: "Case history"
      },
      documents: [],
      interactionHistory: [
        {
          id: "interaction-0",
          actor: "AI Lawyer",
          message: "Earlier legal answer with detailed next steps",
          createdAt: "2026-06-22T09:00:30.000Z"
        },
        {
          id: "interaction-1",
          actor: "You",
          message: "Please continue this very long legal conversation",
          createdAt: "2026-06-22T09:01:00.000Z"
        }
      ]
    },
    selectCase,
    setCaseCommunicationMode,
    isLoadingCases: false,
    caseLoadError: null
  })
}));

describe("Sidebar", () => {
  afterEach(() => {
    cleanup();
    navigate.mockReset();
    selectCase.mockReset();
    setCaseCommunicationMode.mockReset();
  });

  it("builds a compact 20 character chat preview", () => {
    expect(buildChatPreview("You", "Please continue this very long legal conversation")).toBe(
      "You: Please continue..."
    );
  });

  it("shows compact chat previews and opens the selected message in place", async () => {
    const user = userEvent.setup();
    render(<Sidebar />);

    expect(screen.getByText("Please continue this very long legal conversation")).not.toBeNull();
    expect(screen.queryByText("Earlier legal answer with detailed next steps")).toBeNull();
    const chatPreview = screen.getByRole("button", { name: "AI Lawyer: Earlier l..." });

    await user.click(chatPreview);

    expect(selectCase).toHaveBeenCalledWith("case-1");
    expect(setCaseCommunicationMode).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalledWith("/app/chat");
    expect(screen.getByText("Earlier legal answer with detailed next steps")).not.toBeNull();
  });
});
