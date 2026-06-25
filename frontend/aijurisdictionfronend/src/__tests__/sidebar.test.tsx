// @vitest-environment jsdom

import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Sidebar } from "../components/Sidebar";

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
      documents: [
        {
          id: "doc-1",
          caseId: "case-1",
          kind: "generated_document",
          originalFilename: "potvrdenie_o_zaplateni_20260622T120000Z.pdf",
          mimeType: "application/pdf",
          size: 1024,
          sizeLabel: "1 KB",
          uploadedAt: "2026-06-22T09:02:00.000Z"
        }
      ],
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

  it("keeps selected case details collapsed by default while documents remain visible", async () => {
    const user = userEvent.setup();
    render(<Sidebar />);

    expect(screen.queryByText("Please continue this very long legal conversation")).toBeNull();
    expect(screen.queryByText("Earlier legal answer with detailed next steps")).toBeNull();
    const selectedCasePanel = screen.getByText("Case ID").closest(".sidebar-selected-case");
    expect(selectedCasePanel?.hasAttribute("hidden")).toBe(true);
    expect(screen.getByText("potvrdenie_o_zaplateni_20260622T120000Z.pdf")).not.toBeNull();

    await user.click(screen.getByRole("button", { name: "Selected case" }));

    expect(screen.getByText("Case ID")).not.toBeNull();
    expect(selectedCasePanel?.hasAttribute("hidden")).toBe(false);
    expect(screen.getByText("potvrdenie_o_zaplateni_20260622T120000Z.pdf")).not.toBeNull();

    await user.click(screen.getByRole("button", { name: "Selected case" }));

    expect(selectedCasePanel?.hasAttribute("hidden")).toBe(true);
    expect(screen.getByText("potvrdenie_o_zaplateni_20260622T120000Z.pdf")).not.toBeNull();
    expect(screen.queryByRole("button", { name: "AI Lawyer: Earlier l..." })).toBeNull();
    expect(selectCase).not.toHaveBeenCalled();
    expect(setCaseCommunicationMode).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalledWith("/app/chat");
  });
});
