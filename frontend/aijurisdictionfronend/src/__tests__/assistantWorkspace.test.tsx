// @vitest-environment jsdom

import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import AssistantWorkspace, { parseAssistantMessagePresentation } from "../pages/AssistantWorkspace";
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
  assistantModelDisclosureAria: "AI model used for this chat",
  assistantModelDisclosureLabel: "Model",
  assistantComposerLabel: "Assistant message",
  assistantComposerPlaceholder: "Ask for legal research or document preparation...",
  assistantSend: "Send message",
  assistantRole: "Assistant",
  assistantUserRole: "You",
  assistantInitialMessage: "JurisDigta Assistant is ready with JurisDigta API and MCP locked on.",
  assistantEmptyMessageResponse: "Please enter a question or drafting instruction.",
  assistantApiErrorResponse: "The assistant could not reach the JurisDigta API. Status: {status}. Detail: {detail}",
  workspaceConfigurations: "Configurations",
  workspaceSystemLabel: "System",
  workspaceUserLabel: "You",
  workspaceUserVoiceLabel: "You (Voice)",
  workspaceUserVideoLabel: "You (Video)",
  commsTitle: "Communication modes",
  commsSubtitle: "Choose chat, voice, or video agent.",
  commsChat: "Chat",
  commsVoice: "Voice",
  commsVideo: "Video",
  roleSelectorTitle: "Role perspective",
  roleSelectorHint: "Adjust the AI answer to a concrete purpose.",
  workspaceLawyerTitle: "AI lawyer",
  roleIntentLawyer: "Explain my rights",
  workspaceJudgeTitle: "AI judge",
  roleIntentJudge: "Assess fairness",
  workspaceOpposingTitle: "Opposing party",
  roleIntentOpposing: "Challenge my argument"
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

const caseActions = vi.hoisted(() => ({
  setCaseRole: vi.fn(),
  setCaseCommunicationMode: vi.fn(),
  loadCaseData: vi.fn()
}));

vi.mock("../state/CaseProvider", () => ({
  isUserVisibleGeneratedDocument: (document: { kind: string; originalFilename: string }) =>
    document.kind === "generated_document" &&
    !document.originalFilename.toLowerCase().startsWith("assistant-technical-"),
  useCases: () => ({
    activeCase: {
      id: "case-1",
      title: "Case 1",
      documents: [],
      interactionHistory: [
        {
          id: "interaction-1",
          actor: "You",
          message: "Existing client question",
          createdAt: "2026-06-20T00:00:00Z"
        },
        {
          id: "interaction-2",
          actor: "AI Lawyer",
          message: "Existing assistant answer",
          createdAt: "2026-06-20T00:00:01Z"
        }
      ],
      selectedCommunicationMode: "Chat",
      selectedRole: "AI Lawyer"
    },
    loadCaseData: caseActions.loadCaseData,
    setCaseRole: caseActions.setCaseRole,
    setCaseCommunicationMode: caseActions.setCaseCommunicationMode
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
let capturedRuntimeOptions: { initialMessages?: unknown[] } | null = null;

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
  useAuiState: () => null,
  useLocalRuntime: (adapter: typeof capturedAdapter, options?: { initialMessages?: unknown[] }) => {
    capturedAdapter = adapter;
    capturedRuntimeOptions = options ?? null;
    return {};
  }
}));

describe("AssistantWorkspace", () => {
  afterEach(() => {
    capturedAdapter = null;
    capturedRuntimeOptions = null;
    caseActions.setCaseRole.mockReset();
    caseActions.setCaseCommunicationMode.mockReset();
    caseActions.loadCaseData.mockReset();
    vi.mocked(createChatSession).mockReset();
    vi.mocked(streamSession).mockReset();
    cleanup();
  });

  it("renders assistant workspace with configuration controls", () => {
    render(<AssistantWorkspace />);

    expect(screen.getByRole("heading", { name: "JurisDigta Assistant" })).toBeDefined();
    expect(screen.getByLabelText("AI model used for this chat").textContent).toContain("Azure Foundry model");
    expect(screen.getByRole("heading", { name: "Configurations" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Chat" })).toBeDefined();
    expect(screen.getByText("AI lawyer")).toBeDefined();
    expect(screen.getByText("Opposing party")).toBeDefined();
    expect(screen.queryByText("Production access uses JurisDigta account login")).toBeNull();
  });

  it("does not show the static MCP news panel in the assistant workspace", () => {
    render(<AssistantWorkspace />);

    expect(screen.queryByRole("complementary", { name: "Capabilities" })).toBeNull();
    expect(screen.queryByText("JurisDigta API and MCP are always attached.")).toBeNull();
    expect(screen.queryByRole("button", { name: "Current matter" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Legal search" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Verify company" })).toBeNull();
    expect(screen.queryByLabelText(/mcp url/i)).toBeNull();
  });

  it("hydrates the assistant thread from the selected case history", () => {
    render(<AssistantWorkspace />);

    expect(capturedRuntimeOptions?.initialMessages).toEqual([
      expect.objectContaining({
        id: "interaction-1",
        role: "user",
        content: "Existing client question",
        metadata: { custom: { actor: "You" } }
      }),
      expect.objectContaining({
        id: "interaction-2",
        role: "assistant",
        content: "Existing assistant answer",
        metadata: { custom: { actor: "AI Lawyer" } }
      })
    ]);
  });

  it("streams assistant messages from the JurisDigta chat API", async () => {
    const prompt = "Daj mi potvrdenie na zaplatenie 5000 splatne do 31.12.2026";
    vi.mocked(createChatSession).mockResolvedValue({
      id: "session-1",
      user_id: "user-1",
      case_id: "case-1",
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

    expect(createChatSession).toHaveBeenCalledWith({ language: "sk", userId: "user-1", caseId: "case-1" });
    expect(streamSession).toHaveBeenCalledWith({
      sessionId: "session-1",
      instruction: prompt,
      signal: expect.any(AbortSignal)
    });
    expect(caseActions.loadCaseData).toHaveBeenCalledWith("case-1");
    expect(lastResult?.content?.[0]?.text).toBe("Real answer from API");
  });

  it("adds generated document links to the completed assistant response", async () => {
    const prompt = "Vygeneruj finálne splnomocnenie.";
    vi.mocked(createChatSession).mockResolvedValue({
      id: "session-1",
      user_id: "user-1",
      case_id: "case-1",
      country: "SK",
      language: "sk",
      discussion_type: "advice",
      state: "active",
      created_at: "2026-06-20T00:00:00Z"
    });
    vi.mocked(streamSession).mockImplementation(async function* () {
      yield {
        event: "message",
        data: {
          id: "message-1",
          session_id: "session-1",
          role: "assistant",
          content: "Splnomocnenie je pripravené.",
          agent_name: "AI Lawyer",
          created_at: "2026-06-20T00:00:01Z"
        }
      };
      yield {
        event: "done",
        data: { session_id: "session-1", status: "completed" }
      };
    });
    caseActions.loadCaseData.mockResolvedValue({
      id: "case-1",
      title: "Splnomocnenie",
      documents: [
        {
          id: "doc-generated",
          caseId: "case-1",
          kind: "generated_document",
          originalFilename: "splnomocnenie-sk-en.pdf",
          mimeType: "application/pdf",
          size: 0,
          sizeLabel: "processed",
          uploadedAt: "2026-06-20T00:00:02Z"
        }
      ],
      interactionHistory: []
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

    expect(lastResult?.content?.[0]?.text).toContain("Splnomocnenie je pripravené.");
    expect(lastResult?.content?.[0]?.text).toContain("Generated document:");
    expect(lastResult?.content?.[0]?.text).toContain(
      "[splnomocnenie-sk-en.pdf](/app/documents/view?caseId=case-1&docId=doc-generated"
    );
  });

  it("separates document drafts from conversational assistant text for preview rendering", () => {
    const presentation = parseAssistantMessagePresentation(`Pripravim teraz obidve verzie splnomocnenia.

---

**Splnomocnenie (Slovenska verzia)**

Ja, dolu podpisany, tymto splnomocnujem Emiliu Matonokovu, aby v mojom mene vykonavala vsetky ukony spojene s vedenim firemneho motoroveho vozidla PP472DT.

Datum: [datum]
Podpis: ______________________

---

**Power of Attorney (English version)**

I, the undersigned, hereby authorize Emilia Matonokova to perform all actions related to the management of the company vehicle PP472DT.

Date: [date]
Signature: ______________________`);

    expect(presentation.conversationalText).toBe("Pripravim teraz obidve verzie splnomocnenia.");
    expect(presentation.documentPreviews).toHaveLength(2);
    expect(presentation.documentPreviews[0]).toEqual({
      title: "Splnomocnenie (Slovenska verzia)",
      body: expect.stringContaining("Ja, dolu podpisany")
    });
    expect(presentation.documentPreviews[1]?.title).toBe("Power of Attorney (English version)");
    expect(presentation.documentLinks).toEqual([]);
  });

  it("strips internal audience labels and previews a legal draft without separators", () => {
    const presentation = parseAssistantMessagePresentation(`LawyerSlovakia: USER-FACING: Pripravujem splnomocnenie pre Emiliu Testovu na pouzivanie firemneho auta firmy ESolutions SK s.r.o. s nasledujucimi udajmi:

**Splnomocnenie**

**Splnomocnitel:**
Marek Matonok
ESolutions SK s.r.o.
Partizanska 665,
059 18 Spisske Bystre

**Splnomocnenec:**
Emilia Testova

**Predmet splnomocnenia:**
Pouzivanie firemneho auta firmy ESolutions SK s.r.o.

**SPZ vozidla:** PP472DT

**Doba platnosti splnomocnenia:**
Od 1. jula 2026 do 31. decembra 2026

Datum: 25. juna 2026
Podpis: ______________________`);

    expect(presentation.conversationalText).toBe(
      "Pripravujem splnomocnenie pre Emiliu Testovu na pouzivanie firemneho auta firmy ESolutions SK s.r.o. s nasledujucimi udajmi:"
    );
    expect(presentation.conversationalText).not.toContain("USER-FACING");
    expect(presentation.conversationalText).not.toContain("LawyerSlovakia");
    expect(presentation.documentPreviews).toHaveLength(1);
    expect(presentation.documentPreviews[0]).toEqual({
      title: "Splnomocnenie",
      body: expect.stringContaining("Marek Matonok")
    });
    expect(presentation.documentPreviews[0]?.body).toContain("PP472DT");
  });

  it("moves generated PDF links into separate document actions", () => {
    const presentation = parseAssistantMessagePresentation(`Splnomocnenie je pripravene.

Generated document:
- [splnomocnenie-sk-en.pdf](/app/documents/view?caseId=case-1&docId=doc-generated&kind=generated_document)`);

    expect(presentation.conversationalText).toBe("Splnomocnenie je pripravene.");
    expect(presentation.documentPreviews).toEqual([]);
    expect(presentation.documentLinks).toEqual([
      {
        label: "splnomocnenie-sk-en.pdf",
        href: "/app/documents/view?caseId=case-1&docId=doc-generated&kind=generated_document"
      }
    ]);
  });
});
