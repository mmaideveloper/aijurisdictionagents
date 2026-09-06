// @vitest-environment jsdom

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import AssistantWorkspace, { parseAssistantMessagePresentation } from "../pages/AssistantWorkspace";
import { caseThreadKey } from "../pages/assistantWorkspaceUtils";
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
  assistantCorrelationId: "Correlation ID",
  assistantCopyCorrelationId: "Copy ID",
  diagnosticsButton: "Diagnostics",
  diagnosticsOpen: "Open diagnostics",
  diagnosticsEyebrow: "Support reference",
  diagnosticsTitle: "Diagnostics",
  diagnosticsDescription: "Copy this correlation ID and share it with support.",
  diagnosticsClose: "Close diagnostics",
  diagnosticsUnavailableValue: "Not available yet",
  diagnosticsUnavailableHint: "The correlation ID will be available after you send your first message.",
  diagnosticsCopySuccess: "Correlation ID copied to the clipboard.",
  diagnosticsCopyFailed: "The ID could not be copied. Select it above and copy it manually.",
  diagnosticsPrivacyNotice: "Share only this ID for troubleshooting.",
  assistantRole: "Assistant",
  assistantUserRole: "You",
  assistantInitialMessage: "JurisDigta Assistant is ready with JurisDigta API and MCP locked on.",
  assistantEmptyMessageResponse: "Please enter a question or drafting instruction.",
  assistantApiErrorResponse: "Asistent nemohol dokončiť požiadavku na JurisDigta API. Stav: {status}. Detail: {detail}",
  assistantLocalModelTimeout: "Časový limit lokálneho modelu vypršal.",
  assistantExternalModelTimeout: "Časový limit externého modelu vypršal.",
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
  user: { userId: "user-1", email: "admin@example.com" } as { userId?: string; email?: string } | null
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
const clipboardWriteText = vi.fn();

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

it("invalidates a hydrated case thread when an existing message gains presentation content", () => {
  const caseRecord = {
    id: "synthetic-case",
    interactionHistory: [{
      id: "assistant-message",
      createdAt: "2026-09-06T12:00:00Z",
      message: "Working",
    }],
  } as unknown as NonNullable<Parameters<typeof caseThreadKey>[0]>;
  const initialKey = caseThreadKey(caseRecord);

  caseRecord.interactionHistory[0] = {
    id: "assistant-message",
    createdAt: "2026-09-06T12:00:00Z",
    actor: "AI Assistant",
    message: "Completed synthetic document",
    citations: [],
    presentation: {
      schema_version: 1,
      renderer_id: "document_preview",
      renderer_version: 1,
      data: {},
      fallback_text: "Completed synthetic document",
      notices: [],
      citations: [],
      selection: {
        policy_id: "synthetic.presentation.v1",
        reason_code: "test",
        explicit_user_request: true,
        model_proposal_accepted: false,
      },
    },
  };

  expect(caseThreadKey(caseRecord)).not.toBe(initialKey);
});

describe("AssistantWorkspace", () => {
  beforeEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: clipboardWriteText }
    });
    clipboardWriteText.mockResolvedValue(undefined);
    authState.isAuthenticated = true;
    authState.isAuthLoading = false;
    authState.user = { userId: "user-1", email: "admin@example.com" };
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
    clipboardWriteText.mockReset();
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

  it("keeps chat selected and voice/video communication modes unavailable", async () => {
    render(<AssistantWorkspace />);

    const chatMode = screen.getByRole("button", { name: "Chat" });
    const voiceMode = screen.getByRole("button", { name: "Voice" });
    const videoMode = screen.getByRole("button", { name: "Video" });

    expect(chatMode.className).toContain("is-active");
    expect(voiceMode.getAttribute("aria-disabled")).toBe("true");
    expect(videoMode.getAttribute("aria-disabled")).toBe("true");
    expect(voiceMode.getAttribute("title")).toBe("Coming later");
    expect(videoMode.getAttribute("title")).toBe("Coming later");

    fireEvent.click(voiceMode);
    fireEvent.click(videoMode);

    expect(caseActions.setCaseCommunicationMode).not.toHaveBeenCalled();
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
      for await (const unused of result) {
        void unused;
        // consume stream
      }
    } else {
      await result;
    }

    expect(fetchSelectableModelProfiles).toHaveBeenCalledWith({
      userId: "user-1",
      userEmail: "admin@example.com"
    });
    expect(createChatSession).toHaveBeenCalledWith({
      language: "sk",
      userId: "user-1",
      caseId: "case-1",
      modelProfileId: "azure_foundry_gpt_4o_mini",
      correlationId: expect.any(String)
    });
    expect(streamSession).toHaveBeenCalledWith({
      sessionId: "session-1",
      instruction: "Pouzi vybrany model",
      userId: "user-1",
      userEmail: "admin@example.com",
      modelProfileId: "azure_foundry_gpt_4o_mini",
      signal: expect.any(AbortSignal),
      correlationId: expect.any(String)
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
    authState.user = { userId: "user-1", email: "admin@example.com" };
    rerender(<AssistantWorkspace />);

    expect(await screen.findByText("Local Ollama - qwen3:1.7b")).toBeDefined();
    expect(vi.mocked(fetchEffectiveModelRoute)).toHaveBeenCalledWith("user-1");
    expect(vi.mocked(fetchEffectiveModelRoute)).not.toHaveBeenCalledWith(undefined);
  });

  it("uses the signed-in email to load selectable models when the restored session has no user id", async () => {
    authState.user = { email: "admin@example.com" };
    vi.mocked(fetchSelectableModelProfiles).mockResolvedValue({
      eligible: true,
      profiles: [
        {
          model_profile_id: "azurefoundryeu:gpt-5-mini",
          provider: "azurefoundryeu",
          provider_display_name: "azureFoundryEU",
          model: "gpt-5-mini",
          label: "azureFoundryEU - gpt-5-mini",
          is_local: false,
          is_external: true,
          eu_data_zone_capable: true,
          context_window_tokens: 0
        }
      ]
    });

    render(<AssistantWorkspace />);

    expect(await screen.findByRole("combobox", { name: "Select assistant model" })).toBeDefined();
    expect(fetchSelectableModelProfiles).toHaveBeenCalledWith({
      userId: undefined,
      userEmail: "admin@example.com"
    });
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

  it("opens diagnostics and explains that the ID is created after the first message", () => {
    render(<AssistantWorkspace />);

    fireEvent.click(screen.getByRole("button", { name: "Open diagnostics" }));

    expect(screen.getByRole("dialog", { name: "Diagnostics" })).toBeDefined();
    expect(screen.getByText("Not available yet")).toBeDefined();
    expect(screen.getByText("The correlation ID will be available after you send your first message.")).toBeDefined();
    expect((screen.getByRole("button", { name: "Copy ID" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole("dialog", { name: "Diagnostics" }).querySelector('a[href^="mailto:"]')).toBeNull();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Diagnostics" })).toBeNull();
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
      created_at: "2026-06-20T00:00:00Z",
      correlation_id: "corr-visible-303"
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
      modelProfileId: undefined,
      correlationId: expect.any(String)
    });
    expect(streamSession).toHaveBeenCalledWith({
      sessionId: "session-1",
      instruction: prompt,
      userId: "user-1",
      userEmail: "admin@example.com",
      modelProfileId: undefined,
      signal: expect.any(AbortSignal),
      correlationId: "corr-visible-303"
    });
    fireEvent.click(screen.getByRole("button", { name: "Open diagnostics" }));
    expect(screen.getByRole("dialog", { name: "Diagnostics" }).textContent).toContain("corr-visible-303");
    fireEvent.click(screen.getByRole("button", { name: "Copy ID" }));
    await waitFor(() => expect(clipboardWriteText).toHaveBeenCalledWith("corr-visible-303"));
    expect(screen.getByRole("status").textContent).toBe("Correlation ID copied to the clipboard.");
    clipboardWriteText.mockRejectedValueOnce(new Error("clipboard unavailable"));
    fireEvent.click(screen.getByRole("button", { name: "Copy ID" }));
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe(
        "The ID could not be copied. Select it above and copy it manually."
      );
    });
    expect(caseActions.loadCaseData).toHaveBeenCalledWith("case-1");
    expect(lastResult?.content?.[0]?.text).toBe("Real answer from API");
  });

  it("shows the JurisDigta MCP proof notice from backend processing events", async () => {
    const prompt = "Daj mi sumar zo zakona 192/2026";
    const proofNotice =
      "JurisDigta MCP server bol kontaktovaný na získanie najnovších právnych informácií.";
    vi.mocked(createChatSession).mockResolvedValue({
      id: "session-1",
      user_id: "user-1",
      case_id: "case-1",
      country: "SK",
      language: "sk",
      discussion_type: "advice",
      state: "active",
      created_at: "2026-07-14T00:00:00Z"
    });
    vi.mocked(streamSession).mockImplementation(async function* () {
      yield {
        event: "processing",
        data: {
          stage: "mcp_law_context",
          message: proofNotice,
          details: {
            user_visible: true,
            source_notice_i18n: {
              sk: proofNotice,
              de: "Der JurisDigta MCP-Server wurde kontaktiert, um aktuelle Rechtsinformationen abzurufen.",
              en: "JurisDigta MCP Server was contacted to retrieve the latest legal information."
            }
          }
        }
      };
      yield {
        event: "message",
        data: {
          id: "message-1",
          session_id: "session-1",
          role: "assistant",
          content: "Sumar zakona 192/2026 z MCP kontextu.",
          agent_name: "AI Lawyer",
          created_at: "2026-07-14T00:00:01Z"
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

    const streamedTexts: string[] = [];
    if (result && Symbol.asyncIterator in result) {
      for await (const update of result) {
        const text = update.content?.[0]?.text;
        if (text) {
          streamedTexts.push(text);
        }
      }
    } else if (result) {
      const update = await result;
      const text = update.content?.[0]?.text;
      if (text) {
        streamedTexts.push(text);
      }
    }

    expect(streamedTexts[0]).toBe(proofNotice);
    expect(streamedTexts.at(-1)).toBe(`${proofNotice}\n\nSumar zakona 192/2026 z MCP kontextu.`);
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

  it("replaces repeated progress and renders a local timeout without a network error", async () => {
    vi.mocked(createChatSession).mockResolvedValue({
      id: "session-1",
      user_id: "user-1",
      case_id: "case-1",
      country: "SK",
      language: "sk",
      discussion_type: "advice",
      state: "active",
      created_at: "2026-08-05T00:00:00Z"
    });
    vi.mocked(streamSession).mockImplementation(async function* () {
      yield {
        event: "processing",
        data: { stage: "still_working", message: "Stále pracujem na odpovedi." }
      };
      yield {
        event: "processing",
        data: { stage: "still_working", message: "Stále pracujem na odpovedi." }
      };
      yield {
        event: "error",
        data: {
          code: "local_model_timeout",
          message: "Timeout on local model.",
          params: { provider_class: "local", timeout_seconds: 600 }
        }
      };
    });

    render(<AssistantWorkspace />);
    const result = capturedAdapter?.run({
      messages: [{ role: "user", content: [{ type: "text", text: "Jednoduchá testovacia otázka" }] }],
      abortSignal: new AbortController().signal
    });

    const streamedTexts: string[] = [];
    if (result && Symbol.asyncIterator in result) {
      for await (const update of result) {
        const text = update.content?.[0]?.text;
        if (text) streamedTexts.push(text);
      }
    }

    expect(streamedTexts[0]).toBe("Stále pracujem na odpovedi.");
    expect(streamedTexts[1]).toBe("Stále pracujem na odpovedi.");
    expect(streamedTexts.at(-1)).toBe("Časový limit lokálneho modelu vypršal.");
    expect(streamedTexts.at(-1)).not.toContain("network");
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

  it("keeps every numbered section of golden case 602 in one complete document preview", () => {
    const presentation = parseAssistantMessagePresentation(`LawyerSlovakia:

**Potvrdenie o úplnom splatení súkromnej pôžičky**

**1. Údaje o stranách**

| Strana | Údaje |
|---|---|
| **Veriteľ** | Peter Vzorový, adresa: Testová 200, Testovo, Slovensko |
| **Dlžník** | Ján Testovací, adresa: Testová 123, Testovo, Slovensko |

**2. Úvodná veta**
Toto potvrdenie vyjadruje úplné splatenie pôžičky 3 000 EUR.

---

**3. Obsah potvrdenia**
Veriteľ nemá voči dlžníkovi žiadne ďalšie nároky.

---

**4. Podpisy**
Peter Vzorový, podpis: __________________
Ján Testovací, podpis: __________________

---

**5. Dodatočné poznámky**
Potvrdenie je vyhotovené v dvoch rovnocenných vyhotoveniach.

---

**Čo ďalej?**
Pred podpisom skontrolujte všetky údaje.`);

    expect(presentation.documentPreviews).toHaveLength(1);
    expect(presentation.documentPreviews[0]?.title).toBe("Potvrdenie o úplnom splatení súkromnej pôžičky");
    expect(presentation.documentPreviews[0]?.body).toContain("1. Údaje o stranách");
    expect(presentation.documentPreviews[0]?.body).toContain("3. Obsah potvrdenia");
    expect(presentation.documentPreviews[0]?.body).toContain("4. Podpisy");
    expect(presentation.documentPreviews[0]?.body).toContain("5. Dodatočné poznámky");
    expect(presentation.conversationalText).toContain("Čo ďalej?");
    expect(presentation.conversationalText).toContain("Pred podpisom skontrolujte všetky údaje.");
    expect(presentation.conversationalText).not.toContain("LawyerSlovakia");
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
