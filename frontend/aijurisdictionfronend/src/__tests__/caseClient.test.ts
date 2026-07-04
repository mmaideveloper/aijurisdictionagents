// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchCaseDocumentBlob, fetchCaseExportBlob } from "../api/caseClient";

vi.mock("../logging/consoleLogger", () => ({
  consoleLogger: {
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn()
  }
}));

describe("caseClient", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches case documents with the configured API key header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("document body", {
        status: 200,
        headers: {
          "Content-Type": "text/plain",
          "Content-Disposition": 'inline; filename="splnomocnenie.txt"'
        }
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const document = await fetchCaseDocumentBlob({
      userId: "user-1",
      caseId: "case-1",
      docId: "doc-1",
      disposition: "inline"
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/v1/cases/case-1/documents/doc-1?"),
      expect.objectContaining({
        method: "GET",
        headers: {
          "x-api-key": "aijuris"
        }
      })
    );
    expect(fetchMock.mock.calls[0][0]).toContain("user_id=user-1");
    expect(fetchMock.mock.calls[0][0]).toContain("disposition=inline");
    expect(document.contentType).toBe("text/plain");
    expect(document.filename).toBe("splnomocnenie.txt");
    await expect(document.blob.text()).resolves.toBe("document body");
  });

  it("fetches generated documents through the rendered PDF endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("pdf body", {
        status: 200,
        headers: {
          "Content-Type": "application/pdf",
          "Content-Disposition": 'inline; filename="generated.pdf"'
        }
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const document = await fetchCaseDocumentBlob({
      userId: "user-1",
      caseId: "case-1",
      docId: "doc-1",
      disposition: "inline",
      format: "pdf"
    });

    expect(fetchMock.mock.calls[0][0]).toContain("/v1/cases/case-1/documents/doc-1/pdf?");
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        headers: {
          "x-api-key": "aijuris"
        }
      })
    );
    expect(document.contentType).toBe("application/pdf");
    expect(document.filename).toBe("generated.pdf");
  });

  it("fetches a case export zip with the configured API key header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("zip body", {
        status: 200,
        headers: {
          "Content-Type": "application/zip",
          "Content-Disposition": 'attachment; filename="case-export.zip"'
        }
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const exported = await fetchCaseExportBlob({
      userId: "user-1",
      caseId: "case-1"
    });

    expect(fetchMock.mock.calls[0][0]).toContain("/v1/cases/case-1/export?user_id=user-1");
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        method: "GET",
        headers: {
          "x-api-key": "aijuris"
        }
      })
    );
    expect(exported.contentType).toBe("application/zip");
    expect(exported.filename).toBe("case-export.zip");
    await expect(exported.blob.text()).resolves.toBe("zip body");
  });
});
