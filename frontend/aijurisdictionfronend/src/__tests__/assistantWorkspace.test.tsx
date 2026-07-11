// @vitest-environment jsdom

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import AssistantWorkspace, { parseAssistantMessagePresentation } from "../pages/AssistantWorkspace";
import { ApiRequestError, createChatSession, fetchEffectiveModelRoute, fetchSelectableModelProfiles, streamSession } from "../api/chatClient";

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
  assistantModelDisclosurePending: "Checking model route...",
  assistantModelSelectorLabel: "Select assistant model",
  assistantComposerLabel: "Assistant message",
  assistantComposerPlaceholder: "Ask for legal research or document preparation...",
  assistantSend: "Send message",
  assistantRole: "Assistant",
  assistantUserRole: "You",
  assistantInitialMessage: "JurisDigta Assistant is ready with JurisDigta API and MCP locked on.",
  assistantEmptyMessageResponse: "Please enter a question or drafting instruction.",
  assistantApiErrorResponse: "Asistent nemohol dokončiť požiadavku na JurisDigta API. Stav: {status}. Detail: {detail}",
  assistantCaseWriteWindowExpiredDetail:
    "Tento prípad je iba na čítanie, pretože plán {plan} umožňuje úpravy po dobu {days} dňa/dní od vytvorenia.",
  assistantAuthLoadingResponse: "I am checking your account before starting the legal assistant. Please try again in a moment.",
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
  roleIntentOpposing: "Challenge my argument",
  roleUnavailable: "Coming later"
};

vi.mock("../components/LanguageProvider", () => ({
  useLanguage: () => ({
    language: "sk",
    t: (key: string, values?: Record<string, string | number>) => {
      const template = labels[key] ?? key;
      return Object.entries(values ?? {}).reduce(
        (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
        template
      );
    }
  })
}));

const authState = vi.hoisted(() => ({
  isAuthenticated: true,
  isAuthLoading: false,
  user: { userId: "user-1" } as { userId: string } | null
}));

vi.mock("../auth/webAuth", () => ({
  useAuth: () => authState
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
    fetchEffectiveModelRoute: vi.fn(),
    fetchSelectableModelProfiles: vi.fn(),
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
  beforeEach(() => {
    authState.isAuthenticated = true;
    authState.isAuthLoading = false;
    authState.user = { userId: "user-1" };
    vi.mocked(fetchEffectiveModelRoute).mockResolvedValue({
      plan_code: "free",
      route_type: "free_local",
      provider: "local_ollama",
      provider_display_name: "Local Ollama",
      model: "qwen3:1.7b",
      model_profile_id: "local_ollama_default",
      is_local: true,
      is_external: false,
      label: "Local Ollama - qwen3:1.7b"
    });
    vi.mocked(fetchSelectableModelProfiles).mockResolvedValue({ eligible: false, profiles: [] });
  });

  afterEach(() => {
    capturedAdapter = null;
    capturedRuntimeOptions = null;
    caseActions.setCaseRole.mockReset();
    caseActions.setCaseCommunicationMode.mockReset();
    caseActions.loadCaseData.mockReset();
    vi.mocked(createChatSession).mockReset();
    vi.mocked(fetchEffectiveModelRoute).mockReset();
    vi.mocked(fetchSelectableModelProfiles).mockReset();
    vi.mocked(streamSession).mockReset();
    cleanup();
  });

  it("renders assistant workspace with the effective signed-in user model route", async () => {
    vi.mocked(fetchEffectiveModelRoute).mockResolvedValue({
      plan_code: "free",
      route_type: "free_local",
      provider: "local_ollama",
      provider_display_name: "Local Ollama",
      model: "qwen3:1.7b",
      model_profile_id: "local_ollama_default",
      is_local: true,
      is_external: false,
      label: "Local Ollama - qwen3:1.7b"
    });

    render(<AssistantWorkspace />);

    expect(screen.getByRole("heading", { name: "JurisDigta Assistant" })).toBeDefined();
    expect(await screen.findByText("Local Ollama - qwen3:1.7b")).toBeDefined();
    expect(vi.mocked(fetchEffectiveModelRoute)).toHaveBeenCalledWith("user-1");
    expect(screen.getByRole("heading", { name: "Configurations" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Chat" })).toBeDefined();
    expect(screen.getByText("AI lawyer")).toBeDefined();
    expect(screen.getByText("Opposing party")).toBeDefined();
    expect(screen.queryByText("Production access uses JurisDigta account login")).toBeNull();
  });

  it("lets eligible users select a backend-approved assistant model", async () => {
    vi.mocked(fetchSelectableModelProfiles).mockResolvedValue({
      eligible: true,
      profiles: [
        {
          model_profile_id: "azure_foundry_gpt_4o_mini",
          provider: "azure_foundry",
          provider_display_name: "Azure Foundry",
          model: "gpt-4o-mini",
          label: "Azure Foundry - gpt-4o-mini",
          is_local: false,
          is_external: true,
          eu_data_zone_capable: true,
          context_window_tokens: 128000
        }
      ]
    });
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
          content: "Selected model answer",
          agent_name: "AI Lawyer",
          created_at: "2026-06-20T00:00:01Z"
        }
      };
    });

    render(<AssistantWorkspace />);

    const selector = await screen.findByRole("combobox", { name: "Select assistant model" });
    fireEvent.change(selector, { target: { value: "azure_foundry_gpt_4o_mini" } });

    const result = capturedAdapter?.run({
      messages: [
        {
          role: "user",
          content: [{ type: "text", text: "Pouzi vybrany model" }]
        }
      ],
      abortSignal: new AbortController().signal
    });

    if (result && Symbol.asyncIterator in result) {
      for await (const _update of result) {
        // consume stream
      }
    } else {
      await result;
    }

    expect(fetchSelectableModelProfiles).toHaveBeenCalledWith("user-1");
    expect(createChatSession).toHaveBeenCalledWith({
      language: "sk",
      userId: "user-1",
      caseId: "case-1",
      modelProfileId: "azure_foundry_gpt_4o_mini"
    });
    expect(streamSession).toHaveBeenCalledWith({
      sessionId: "session-1",
      instruction: "Pouzi vybrany model",
      modelProfileId: "azure_foundry_gpt_4o_mini",
      signal: expect.any(AbortSignal)
    });
  });

  it("waits for the signed-in user id before showing the effective model route", async () => {
    authState.isAuthenticated = true;
    authState.isAuthLoading = true;
    authState.user = null;
    const { rerender } = render(<AssistantWorkspace />);

    expect(screen.getByLabelText("AI model used for this chat").textContent).toContain("Checking model route...");
    expect(vi.mocked(fetchEffectiveModelRoute)).not.toHaveBeenCalled();

    authState.isAuthLoading = false;
    authState.user = { userId: "user-1" };
    rerender(<AssistantWorkspace />);

    expect(await screen.findByText("Local Ollama - qwen3:1.7b")).toBeDefined();
    expect(vi.mocked(fetchEffectiveModelRoute)).toHaveBeenCalledWith("user-1");
    expect(vi.mocked(fetchEffectiveModelRoute)).not.toHaveBeenCalledWith(undefined);
  });

  it("does not create a chat session until a signed-in user id is available", async () => {
    authState.isAuthenticated = true;
    authState.isAuthLoading = true;
    authState.user = null;

    render(<AssistantWorkspace />);

    const result = capturedAdapter?.run({
      messages: [
        {
          role: "user",
          content: [{ type: "text", text: "Priprav splnomocnenie." }]
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

    expect(createChatSession).not.toHaveBeenCalled();
    expect(streamSession).not.toHaveBeenCalled();
    expect(lastResult?.content?.[0]?.text).toBe(
      "I am checking your account before starting the legal assistant. Please try again in a moment."
    );
  });

  it("falls back to the configured model label when route disclosure is unavailable", () => {
    authState.isAuthenticated = false;
    authState.user = null;
    vi.mocked(fetchEffectiveModelRoute).mockRejectedValue(new Error("offline"));

    render(<AssistantWorkspace />);

    expect(screen.getByLabelText("AI model used for this chat").textContent).toContain("Azure Foundry model");
  });

  it("keeps unsupported legal-risk roles disabled in the configuration panel", () => {
    render(<AssistantWorkspace />);

    const lawyerRole = screen.getByRole("radio", { name: /AI lawyer/i }) as HTMLInputElement;
    const judgeRole = screen.getByRole("radio", { name: /AI judge/i }) as HTMLInputElement;
    const opposingRole = screen.getByRole("radio", { name: /Opposing party/i }) as HTMLInputElement;

    expect(lawyerRole.checked).toBe(true);
    expect(lawyerRole.disabled).toBe(false);
    expect(judgeRole.disabled).toBe(true);
    expect(opposingRole.disabled).toBe(true);
    expect(screen.getAllByText("Coming later")).toHaveLength(2);
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

    expect(createChatSession).toHaveBeenCalledWith({
      language: "sk",
      userId: "user-1",
      caseId: "case-1",
      modelProfileId: undefined
    });
    expect(streamSession).toHaveBeenCalledWith({
      sessionId: "session-1",
      instruction: prompt,
      modelProfileId: undefined,
      signal: expect.any(AbortSignal)
    });
    expect(caseActions.loadCaseData).toHaveBeenCalledWith("case-1");
    expect(lastResult?.content?.[0]?.text).toBe("Real answer from API");
  });

  it("localizes expired free-plan write errors from the JurisDigta chat API", async () => {
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
      if (Date.now() < 0) {
        yield undefined as never;
      }
      throw new ApiRequestError(
        "http",
        "Case is read-only because the Free plan allows edits for 1 day(s) after creation.",
        403,
        {
          code: "case_write_window_expired",
          params: { plan: "Free", days: 1 }
        }
      );
    });

    render(<AssistantWorkspace />);

    const result = capturedAdapter?.run({
      messages: [
        {
          role: "user",
          content: [{ type: "text", text: "Pokračuj v prípade" }]
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

    expect(lastResult?.content?.[0]?.text).toContain("Tento prípad je iba na čítanie");
    expect(lastResult?.content?.[0]?.text).not.toContain("Case is read-only");
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

  it("uses hydrated generated document history instead of a terminal PDF progress sentence", async () => {
    const prompt = "Priprav splnomocnenie.";
    vi.mocked(createChatSession).mockResolvedValue({
      id: "session-1",
      user_id: "user-1",
      case_id: "case-1",
      country: "SK",
      language: "sk",
      discussion_type: "advice",
      state: "active",
      created_at: "2026-07-09T00:00:00Z"
    });
    vi.mocked(streamSession).mockImplementation(async function* () {
      yield {
        event: "message",
        data: {
          id: "message-1",
          session_id: "session-1",
          role: "assistant",
          content: "Teraz vytvorÃ­m PDF dokument. ChvÃ­Ä¾u prosÃ­m.",
          agent_name: "AI Lawyer",
          created_at: "2026-07-09T00:00:01Z"
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
          originalFilename: "splnomocnenie.pdf",
          mimeType: "application/pdf",
          size: 0,
          sizeLabel: "processed",
          uploadedAt: "2026-07-09T00:00:02Z"
        }
      ],
      interactionHistory: [
        {
          id: "message-1",
          actor: "AI Lawyer",
          createdAt: "2026-07-09T00:00:02Z",
          message: `Splnomocnenie je pripravene.

**Splnomocnenie**

Ja, dolu podpisany, tymto splnomocnujem Emiliu Testovu.

Datum: 9. jula 2026
Podpis: ______________________

Generated document:
- [splnomocnenie.pdf](/app/documents/view?caseId=case-1&docId=doc-generated&kind=generated_document)`,
          citations: []
        }
      ]
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

    expect(lastResult?.content?.[0]?.text).toContain("**Splnomocnenie**");
    expect(lastResult?.content?.[0]?.text).toContain("[splnomocnenie.pdf](/app/documents/view?caseId=case-1&docId=doc-generated");
    expect(lastResult?.content?.[0]?.text).not.toContain("Teraz vytvorÃ­m PDF dokument");
    expect(lastResult?.content?.[0]?.text?.match(/Generated document:/g)).toHaveLength(1);
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

  it("removes fake relative document download links from assistant history", () => {
    const presentation = parseAssistantMessagePresentation(`USER-FACING: Splnomocnenie bolo uspesne pripravene a je pripravene na stiahnutie.

Mozete si ho stiahnut pomocou nasledujuceho odkazu:

[Stiahnut splnomocnenie](documents/splnomocnenie_ESolutions_SK.pdf)

    Generated document:
- [splnomocnenie_ESolutions_SK.pdf](/app/documents/view?caseId=case-1&docId=doc-generated&kind=generated_document)`);

    expect(presentation.conversationalText).toBe(
      "Splnomocnenie bolo uspesne pripravene a je pripravene na stiahnutie."
    );
    expect(presentation.conversationalText).not.toContain("USER-FACING");
    expect(presentation.documentLinks).toEqual([
      {
        label: "splnomocnenie_ESolutions_SK.pdf",
        href: "/app/documents/view?caseId=case-1&docId=doc-generated&kind=generated_document"
      }
    ]);
  });
});
