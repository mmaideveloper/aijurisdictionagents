// @vitest-environment jsdom

import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AssistantWorkspace from "../pages/AssistantWorkspace";
import { createChatSession, replyToSession } from "../api/chatClient";

const labels: Record<string, string> = {
  assistantThreadsTitle: "Conversations",
  assistantThreadCurrent: "Current matter",
  assistantThreadDocument: "Document preparation",
  assistantEyebrow: "Authenticated legal assistant",
  assistantTitle: "JurisDigta Assistant",
  assistantSubtitle: "Assistant subtitle",
  assistantApiAuthAccess: "Production access uses JurisDigta account login",
  assistantModesTitle: "Assistant modes",
  assistantModeLegalSearch: "Legal search",
  assistantModePrepareDocument: "Prepare document",
  assistantModeDraftDocument: "Draft document",
  assistantModeVerifyPerson: "Verify person",
  assistantModeVerifyCompany: "Verify company",
  assistantModeScreenPerson: "Screen person",
  assistantModeScreenCompany: "Screen company",
  assistantModeVerifyCar: "Verify car",
  assistantModeVerifyLocation: "Verify location",
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
    isAuthenticated: true,
    signOut: vi.fn(),
    user: { userId: "user-1" }
  })
}));

vi.mock("../state/CaseProvider", () => ({
  useCases: () => ({
    activeCase: null,
    cases: [],
    documents: [],
    selectCase: vi.fn(),
    addInteraction: vi.fn()
  })
}));

vi.mock("../api/chatClient", async () => {
  const actual = await vi.importActual<typeof import("../api/chatClient")>("../api/chatClient");
  return {
    ...actual,
    createChatSession: vi.fn(),
    replyToSession: vi.fn()
  };
});

let capturedAdapter: { run: (options: unknown) => Promise<{ content?: readonly { type: string; text?: string }[] }> } | null =
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
    vi.mocked(replyToSession).mockReset();
    cleanup();
  });

  const renderAssistantWorkspace = () =>
    render(
      <MemoryRouter>
        <AssistantWorkspace />
      </MemoryRouter>
    );

  it("renders the locked JurisDigta MCP and compliance guardrails", () => {
    renderAssistantWorkspace();

    expect(screen.getByRole("heading", { name: "JurisDigta Assistant" })).toBeDefined();
    expect(screen.getByText("Locked on")).toBeDefined();
    expect(screen.getByText("Human approval")).toBeDefined();
    expect(screen.getByText("AI-assisted draft")).toBeDefined();
    expect(screen.getByText("Production access uses JurisDigta account login")).toBeDefined();
  });

  it("shows V1 assistant modes without arbitrary MCP URL entry", () => {
    renderAssistantWorkspace();

    expect(screen.getByRole("button", { name: "Legal search" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Verify company" })).toBeDefined();
    expect(screen.queryByLabelText(/mcp url/i)).toBeNull();
  });

  it("sends assistant messages to the JurisDigta chat API", async () => {
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
    vi.mocked(replyToSession).mockResolvedValue({
      id: "message-1",
      session_id: "session-1",
      role: "assistant",
      content: "Real answer from API",
      agent_name: "AI Lawyer",
      created_at: "2026-06-20T00:00:01Z"
    });

    renderAssistantWorkspace();

    const result = await capturedAdapter?.run({
      messages: [
        {
          role: "user",
          content: [{ type: "text", text: "Daj mi potvrdenie na zaplatenie 5000 splatné do 31.12.2026" }]
        }
      ]
    });

    expect(createChatSession).toHaveBeenCalledWith({ language: "sk", userId: "user-1" });
    expect(replyToSession).toHaveBeenCalledWith({
      sessionId: "session-1",
      content: "Daj mi potvrdenie na zaplatenie 5000 splatné do 31.12.2026"
    });
    expect(result?.content?.[0]?.text).toBe("Real answer from API");
  });
});
