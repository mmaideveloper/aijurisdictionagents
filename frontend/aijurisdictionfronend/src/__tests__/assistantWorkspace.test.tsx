// @vitest-environment jsdom

import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import AssistantWorkspace from "../pages/AssistantWorkspace";
import { createChatSession, streamSession } from "../api/chatClient";

const labels: Record<string, string> = {
  assistantThreadsTitle: "Conversations",
  assistantThreadCurrent: "Current matter",
  assistantThreadDocument: "Document preparation",
  assistantEyebrow: "Authenticated legal assistant",
  assistantTitle: "JurisDigta Assistant",
  assistantSubtitle: "Assistant subtitle",
  assistantToolsTitle: "Capabilities",
  assistantMandatoryMcpTitle: "JurisDigta MCP",
  assistantMandatoryMcpBody: "JurisDigta API and MCP are always attached.",
  assistantMcpLocked: "Locked on",
  assistantCapabilityLawSearch: "Law search and law text",
  assistantCapabilityOrsr: "ORSR company lookup placeholder",
  assistantCapabilityPerson: "Consent-gated person verification placeholder",
  assistantCapabilityScreening: "Person and company screening placeholder",
  assistantCapabilityCar: "Car validation placeholder",
  assistantCapabilityLocation: "Location validation placeholder",
  assistantApprovalTitle: "Human approval",
  assistantApprovalBody: "Sensitive tool calls require explicit approval.",
  assistantMetadataTitle: "Transparency metadata",
  assistantMetadataGenerated: "Generated output",
  assistantMetadataAiDraft: "AI-assisted draft",
  assistantMetadataRisk: "Risk level",
  assistantMetadataRiskValue: "Legal review required",
  assistantMetadataReview: "Human oversight",
  assistantMetadataReviewValue: "Required before final use",
  assistantComposerLabel: "Assistant message",
  assistantComposerPlaceholder: "Ask for legal research or document preparation...",
  assistantSend: "Send message",
  assistantRole: "Assistant",
  assistantUserRole: "You",
  assistantInitialMessage: "JurisDigta Assistant is ready with JurisDigta API and MCP locked on.",
  assistantEmptyMessageResponse: "Please enter a question or drafting instruction.",
  assistantApiErrorResponse: "The assistant could not reach the JurisDigta API. Status: {status}. Detail: {detail}"
};

vi.mock("../components/LanguageProvider", () => ({
  useLanguage: () => ({
    language: "sk",
    t: (key: string) => labels[key] ?? key
  })
}));

vi.mock("../auth/webAuth", () => ({
  useAuth: () => ({
    user: { userId: "user-1" }
  })
}));

vi.mock("../api/chatClient", async () => {
  const actual = await vi.importActual<typeof import("../api/chatClient")>("../api/chatClient");
  return {
    ...actual,
    createChatSession: vi.fn(),
    streamSession: vi.fn()
  };
});

type CapturedRunResult = { content?: readonly { type: string; text?: string }[] };

let capturedAdapter: { run: (options: unknown) => AsyncGenerator<CapturedRunResult, void> | Promise<CapturedRunResult> } | null =
  null;

vi.mock("@assistant-ui/react", () => ({
  AssistantRuntimeProvider: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ComposerPrimitive: {
    Root: ({ children, className }: { children: React.ReactNode; className?: string }) => (
      <form className={className}>{children}</form>
    ),
    Input: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...props} />,
    Send: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
      <button type="button" {...props}>
        {children}
      </button>
    )
  },
  MessagePrimitive: {
    Root: ({ children, className }: { children: React.ReactNode; className?: string }) => (
      <article className={className}>{children}</article>
    ),
    If: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    Parts: () => <p>JurisDigta Assistant is ready with JurisDigta API and MCP locked on.</p>
  },
  ThreadPrimitive: {
    Root: ({ children, className }: { children: React.ReactNode; className?: string }) => (
      <section className={className}>{children}</section>
    ),
    Viewport: ({ children, className }: { children: React.ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
    Messages: ({ components }: { components: { Message: React.FC } }) => {
      const Message = components.Message;
      return <Message />;
    }
  },
  useLocalRuntime: (adapter: typeof capturedAdapter) => {
    capturedAdapter = adapter;
    return {};
  }
}));

describe("AssistantWorkspace", () => {
  afterEach(() => {
    capturedAdapter = null;
    vi.mocked(createChatSession).mockReset();
    vi.mocked(streamSession).mockReset();
    cleanup();
  });

  it("renders the locked JurisDigta MCP and compliance guardrails", () => {
    render(<AssistantWorkspace />);

    expect(screen.getByRole("heading", { name: "JurisDigta Assistant" })).toBeDefined();
    expect(screen.getByText("Locked on")).toBeDefined();
    expect(screen.getByText("Human approval")).toBeDefined();
    expect(screen.getByText("AI-assisted draft")).toBeDefined();
    expect(screen.queryByText("Production access uses JurisDigta account login")).toBeNull();
  });

  it("does not show assistant modes or arbitrary MCP URL entry", () => {
    render(<AssistantWorkspace />);

    expect(screen.queryByRole("button", { name: "Legal search" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Verify company" })).toBeNull();
    expect(screen.queryByLabelText(/mcp url/i)).toBeNull();
  });

  it("streams assistant messages from the JurisDigta chat API", async () => {
    const prompt = "Daj mi potvrdenie na zaplatenie 5000 splatne do 31.12.2026";
    vi.mocked(createChatSession).mockResolvedValue({
      id: "session-1",
      user_id: "user-1",
      case_id: null,
      country: "SK",
      language: "sk",
      discussion_type: "advice",
      state: "active",
      created_at: "2026-06-20T00:00:00Z"
    });
    vi.mocked(streamSession).mockImplementation(async function* () {
      yield {
        event: "processing",
        data: { stage: "thinking", message: "Thinking with JurisDigta..." }
      };
      yield {
        event: "message",
        data: {
          id: "message-1",
          session_id: "session-1",
          role: "assistant",
          content: "Real answer from API",
          agent_name: "AI Lawyer",
          created_at: "2026-06-20T00:00:01Z"
        }
      };
      yield {
        event: "done",
        data: { session_id: "session-1", status: "completed" }
      };
    });

    render(<AssistantWorkspace />);

    const result = capturedAdapter?.run({
      messages: [
        {
          role: "user",
          content: [{ type: "text", text: prompt }]
        }
      ],
      abortSignal: new AbortController().signal
    });

    let lastResult: CapturedRunResult | undefined;
    if (result && Symbol.asyncIterator in result) {
      for await (const update of result) {
        lastResult = update;
      }
    } else {
      lastResult = await result;
    }

    expect(createChatSession).toHaveBeenCalledWith({ language: "sk", userId: "user-1" });
    expect(streamSession).toHaveBeenCalledWith({
      sessionId: "session-1",
      instruction: prompt,
      signal: expect.any(AbortSignal)
    });
    expect(lastResult?.content?.[0]?.text).toBe("Real answer from API");
  });
});
