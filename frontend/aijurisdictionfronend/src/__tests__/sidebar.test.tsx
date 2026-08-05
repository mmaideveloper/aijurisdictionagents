// @vitest-environment jsdom

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Sidebar } from "../components/Sidebar";

const navigate = vi.fn();
const selectCase = vi.fn();
const setCaseCommunicationMode = vi.fn();
const deleteCase = vi.fn();
const deleteDocument = vi.fn();

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
    t: (key: string, values?: Record<string, string>) =>
      ({
        appName: "JurisDigta AI právnik",
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
        profileCaseExport: "Export case",
        profileCaseExportFailed: "Could not export case.",
        profileCaseExportStarted: "Case export download started.",
        sidebarDeleteDocument: `Delete document ${values?.filename ?? ""}`,
        sidebarDeleteDocumentConfirm: `Permanently delete ${values?.filename ?? ""}?`,
        sidebarDeleteDocumentSuccess: "Document deleted and recorded in the case history.",
        sidebarDeleteDocumentFailed: "Could not delete the document.",
        sidebarDeleteCase: "Delete case",
        sidebarDeleteCaseConfirm: `Soft-delete case ${values?.title ?? ""}?`,
        sidebarDeleteCaseSuccess: "Case deleted.",
        sidebarDeleteCaseFailed: "Could not delete the case.",
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
    deleteCase,
    deleteDocument,
    setCaseCommunicationMode,
    isLoadingCases: false,
    caseLoadError: null
  })
}));

describe("Sidebar", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    URL.createObjectURL = vi.fn(() => "blob:active-case-export");
    URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    cleanup();
    navigate.mockReset();
    selectCase.mockReset();
    setCaseCommunicationMode.mockReset();
    deleteCase.mockReset();
    deleteDocument.mockReset();
  });

  it("downloads the active case export and reports that the download started", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response("zip", {
        status: 200,
        headers: {
          "Content-Type": "application/zip",
          "Content-Disposition": 'attachment; filename="active-case-export.zip"'
        }
      })
    );
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const user = userEvent.setup();

    render(<Sidebar />);
    await user.click(screen.getByRole("button", { name: "Export case" }));

    await waitFor(() => expect(clickSpy).toHaveBeenCalledOnce());
    expect(screen.getByRole("status").textContent).toBe("Case export download started.");
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/v1/cases/case-1/export?user_id=user-1"),
      expect.objectContaining({ method: "GET" })
    );

    clickSpy.mockRestore();
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

  it("confirms and deletes a document without opening it", async () => {
    const confirm = vi.fn(() => true);
    vi.stubGlobal("confirm", confirm);
    deleteDocument.mockResolvedValueOnce(undefined);
    const user = userEvent.setup();

    render(<Sidebar />);
    await user.click(
      screen.getByRole("button", {
        name: "Delete document potvrdenie_o_zaplateni_20260622T120000Z.pdf"
      })
    );

    expect(confirm).toHaveBeenCalledWith(
      "Permanently delete potvrdenie_o_zaplateni_20260622T120000Z.pdf?"
    );
    await waitFor(() => expect(deleteDocument).toHaveBeenCalledWith("case-1", "doc-1"));
    expect(screen.getByRole("status").textContent).toBe(
      "Document deleted and recorded in the case history."
    );
  });

  it("confirms and soft-deletes the active case", async () => {
    const confirm = vi.fn(() => true);
    vi.stubGlobal("confirm", confirm);
    deleteCase.mockResolvedValueOnce(undefined);
    const user = userEvent.setup();

    render(<Sidebar />);
    await user.click(screen.getByRole("button", { name: "Delete case" }));

    expect(confirm).toHaveBeenCalledWith("Soft-delete case Stored case?");
    await waitFor(() => expect(deleteCase).toHaveBeenCalledWith("case-1"));
    expect(screen.getByRole("status").textContent).toBe("Case deleted.");
  });
});
