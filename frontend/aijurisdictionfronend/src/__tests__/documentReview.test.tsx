// @vitest-environment jsdom
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DocumentReview } from "../components/DocumentReview";

vi.mock("../auth/webAuth", () => ({ useAuth: () => ({ user: { deviceId: "test-device", deviceAuthToken: "test-only-token" } }) }));
vi.mock("../api/chatClient", () => ({ chatApiRuntimeConfig: () => ({ baseUrl: "http://localhost", apiKey: "test" }), parseApiErrorResponse: async () => ({ message: "Reload before saving" }) }));
afterEach(() => { vi.unstubAllGlobals(); });

describe("Document review decisions", () => {
  it("uses authenticated requests, server preview and revision-bound decisions", async () => {
    const review = { review_id: "r", revision: 1, paragraphs: ["Old clause"], warning: "Review required",
      review_date: "2026-09-10", questions: [], citations: [], preview_text: "Old clause\nReview required",
      proposals: [{ id: "0", paragraph: 0, original: "Old clause", replacement: "New clause", reason: "Synthetic reason", source_ids: [], section: "", decision: "pending" }] };
    const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ text: "Old clause", review })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...review, revision: 2, preview_text: "Server accepted preview",
        proposals: [{ ...review.proposals[0], decision: "accepted" }] })));
    vi.stubGlobal("fetch", fetch);
    render(<DocumentReview caseId="c" docId="d" userId="u" />);
    await screen.findByText("Synthetic reason");
    expect((screen.getByText("Stiahnuť DOCX") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByText("Prijať"));
    await screen.findByText("Server accepted preview");
    const request = fetch.mock.calls[1][1];
    expect(JSON.parse(request.body)).toEqual({ expected_revision: 1, decisions: { "0": "accepted" } });
    expect(request.headers["x-jurisdigta-device-id"]).toBe("test-device");
    await waitFor(() => expect((screen.getByText("Stiahnuť DOCX") as HTMLButtonElement).disabled).toBe(false));
  });
});
