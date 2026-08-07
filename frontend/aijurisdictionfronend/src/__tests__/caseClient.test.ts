// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";
import {
  deleteApiCase,
  deleteApiCaseDocument,
  fetchCaseDocumentBlob,
  fetchCaseExportBlob
} from "../api/caseClient";

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

  it("deletes a case document and returns its audit tombstone", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      Response.json({
        event_id: "event-1",
        case_id: "case-1",
        doc_id: "doc-1",
        document_kind: "uploaded",
        outcome: "deleted",
        deleted_at: "2026-08-05T13:00:00Z",
        communication_id: "communication-1",
        correlation_id: "correlation-1"
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await deleteApiCaseDocument("user-1", "case-1", "doc-1");

    expect(fetchMock.mock.calls[0][0]).toContain(
      "/v1/cases/case-1/documents/doc-1?user_id=user-1"
    );
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({ method: "DELETE", headers: { "x-api-key": "aijuris" } })
    );
    expect(result.outcome).toBe("deleted");
    expect(result.correlation_id).toBe("correlation-1");
  });

  it("soft-deletes a case with the configured API key header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await deleteApiCase("user-1", "case-1");

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/v1/cases/case-1?user_id=user-1"),
      expect.objectContaining({ method: "DELETE", headers: { "x-api-key": "aijuris" } })
    );
  });
});
