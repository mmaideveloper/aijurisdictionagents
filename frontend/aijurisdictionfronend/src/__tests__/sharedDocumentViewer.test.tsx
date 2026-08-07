// @vitest-environment jsdom
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LanguageProvider } from "../components/LanguageProvider";
import SharedDocumentViewer from "../pages/SharedDocumentViewer";
import * as shareClient from "../api/documentShareClient";

vi.mock("../api/documentShareClient", () => ({
  requestDocumentShareCode: vi.fn(),
  verifyDocumentShareCode: vi.fn(),
  fetchSharedDocumentPdf: vi.fn()
}));

describe("Shared document viewer", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(shareClient.requestDocumentShareCode).mockResolvedValue({ message: "sent", locale: "sk" });
    vi.mocked(shareClient.verifyDocumentShareCode).mockResolvedValue({ session_token: "session-token", expires_at: "2030-01-01T00:00:00Z", locale: "sk" });
    vi.mocked(shareClient.fetchSharedDocumentPdf).mockResolvedValue(new Blob(["%PDF"], { type: "application/pdf" }));
    vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:document"), revokeObjectURL: vi.fn() });
  });

  it("uses Slovak verification copy and opens only the verified PDF", async () => {
    render(
      <LanguageProvider><MemoryRouter initialEntries={["/shared-documents/share-token"]}>
        <Routes><Route path="/shared-documents/:shareToken" element={<SharedDocumentViewer />} /></Routes>
      </MemoryRouter></LanguageProvider>
    );
    fireEvent.click(screen.getByRole("button", { name: "Odoslať overovací kód" }));
    await screen.findByText("Overovací kód bol odoslaný na e-mail príjemcu.");
    fireEvent.change(screen.getByLabelText("Šesťmiestny overovací kód"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Overiť a otvoriť dokument" }));
    await waitFor(() => expect(shareClient.fetchSharedDocumentPdf).toHaveBeenCalledWith("session-token"));
    expect(screen.getByTitle("Chránený právny dokument").getAttribute("src")).toBe("blob:document");
  });
});
