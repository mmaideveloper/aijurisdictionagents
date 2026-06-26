// @vitest-environment jsdom

import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CaseIntake from "../pages/CaseIntake";

const createCaseMock = vi.fn();
const navigateMock = vi.fn();

vi.mock("../state/CaseProvider", () => ({
  useCases: () => ({
    createCase: createCaseMock
  })
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => navigateMock
}));

const labels: Record<string, string> = {
  caseTitle: "Create a case",
  caseSubtitle: "Upload documents and open a chatbot with the AI lawyer agent.",
  caseDetailsTitle: "Case details",
  caseNameLabel: "Case name",
  caseNamePlaceholder: "Regulatory review - Q2",
  caseJurisdiction: "Jurisdiction",
  caseJurisdictionPlaceholder: "EU / Slovakia",
  caseOpposingLabel: "Opposing party",
  caseOpposingPlaceholder: "Plaintiff / Prosecutor",
  caseUpload: "Upload evidence",
  caseUploadBody: "Drag documents or upload PDF, DOCX, evidence packs.",
  caseUploadButton: "Upload files",
  caseUploadOptional: "Uploading documents is optional. You can create the case first and add files later.",
  caseFieldRequired: "This field is required.",
  caseFormValidationMessage: "Fill out all case fields before creating the case.",
  caseSelectedFilesTitle: "Selected files",
  caseNoFilesSelected: "No documents selected yet.",
  caseRemoveFile: "Remove",
  caseStorageMode: "Stored in your JurisDigta case data.",
  caseStartChat: "Start AI lawyer chat"
};

vi.mock("../components/LanguageProvider", () => ({
  useLanguage: () => ({
    t: (key: string) => labels[key] ?? key
  })
}));

describe("Case intake page", () => {
  beforeEach(() => {
    cleanup();
    createCaseMock.mockReset();
    navigateMock.mockReset();
  });

  it("shows validation errors when required fields are missing", async () => {
    const user = userEvent.setup();
    render(<CaseIntake />);

    await user.click(screen.getByRole("button", { name: "Start AI lawyer chat" }));

    expect(screen.getAllByText("This field is required.")).toHaveLength(1);
    expect(screen.getByText("Fill out all case fields before creating the case.")).toBeDefined();
    expect(createCaseMock).not.toHaveBeenCalled();
  });

  it("prepopulates Slovak default case values", () => {
    render(<CaseIntake />);

    expect((screen.getByLabelText("Jurisdiction") as HTMLInputElement).value).toBe("Slovensko");
    expect((screen.getByLabelText("Opposing party") as HTMLInputElement).value).toBe("ziadna");
  });

  it("creates a mock case without uploaded documents", async () => {
    const user = userEvent.setup();
    render(<CaseIntake />);

    await user.type(screen.getByLabelText("Case name"), "No-doc intake");

    await user.click(screen.getByRole("button", { name: "Start AI lawyer chat" }));

    expect(createCaseMock).toHaveBeenCalledTimes(1);
    expect(createCaseMock).toHaveBeenCalledWith({
      title: "No-doc intake",
      jurisdiction: "Slovensko",
      opposingParty: "ziadna",
      documents: []
    });
    expect(navigateMock).toHaveBeenCalledWith("/app/assistant", { replace: true });
  });

  it("creates a mock case and navigates to the assistant workspace when the form is complete", async () => {
    const user = userEvent.setup();
    render(<CaseIntake />);

    await user.type(screen.getByLabelText("Case name"), "Contract dispute intake");
    await user.clear(screen.getByLabelText("Jurisdiction"));
    await user.type(screen.getByLabelText("Jurisdiction"), "Slovakia");
    await user.clear(screen.getByLabelText("Opposing party"));
    await user.type(screen.getByLabelText("Opposing party"), "Northwind LLC");

    const file = new File(["sample pdf"], "dispute-brief.pdf", {
      type: "application/pdf"
    });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);

    await user.click(screen.getByRole("button", { name: "Start AI lawyer chat" }));

    expect(createCaseMock).toHaveBeenCalledTimes(1);
    expect(createCaseMock).toHaveBeenCalledWith({
      title: "Contract dispute intake",
      jurisdiction: "Slovakia",
      opposingParty: "Northwind LLC",
      documents: [
        {
          originalFilename: "dispute-brief.pdf",
          mimeType: "application/pdf",
          size: file.size,
          file
        }
      ]
    });
    expect(navigateMock).toHaveBeenCalledWith("/app/assistant", { replace: true });
  });
});
