// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";
import { submitAssistantQuestion } from "../assistantGateway";
import { createChatSession, replyToSession } from "../api/chatClient";

vi.mock("../api/chatClient", () => ({
  createChatSession: vi.fn(),
  replyToSession: vi.fn()
}));

describe("assistantGateway", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("uses the real chat API instead of local demo text when Assistant Gateway returns 405", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 405
      })
    );
    vi.mocked(createChatSession).mockResolvedValue({
      id: "session-1",
      user_id: null,
      case_id: null,
      country: "SK",
      language: "sk",
      discussion_type: "advice",
      state: "active",
      created_at: "2026-06-20T00:00:00Z"
    });
    vi.mocked(replyToSession).mockResolvedValue({
      id: "message-1",
      session_id: "session-1",
      role: "assistant",
      content: "Skutocna odpoved z JurisDigta chat API.",
      agent_name: "AI Lawyer",
      created_at: "2026-06-20T00:00:01Z"
    });

    const response = await submitAssistantQuestion({
      question: "Daj mi potvrdenie na zaplatenie 5000 splatne do 31.12.2026",
      caseMode: "new",
      caseId: "",
      country: "SK",
      language: "sk",
      consentGateway: true,
      consentDocuments: true,
      consentThirdParty: false,
      files: []
    });

    expect(createChatSession).toHaveBeenCalledWith({
      caseId: undefined,
      country: "SK",
      language: "sk"
    });
    expect(replyToSession).toHaveBeenCalledWith({
      sessionId: "session-1",
      content: expect.stringContaining("Daj mi potvrdenie na zaplatenie 5000")
    });
    expect(response.answer).toBe("Skutocna odpoved z JurisDigta chat API.");
    expect(response.usedFallback).toBe(false);
    expect(response.answer).not.toContain("Local demo answer");
    expect(response.answer).not.toContain("Gateway note");
  });
});
