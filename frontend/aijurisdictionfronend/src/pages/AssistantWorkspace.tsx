import React from "react";
import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
  useLocalRuntime,
  useMessagePartText,
  type ChatModelAdapter,
  type ThreadMessageLike
} from "@assistant-ui/react";
import { BsArrowUpCircle } from "react-icons/bs";
import { FiMessageSquare, FiMic, FiVideo } from "react-icons/fi";
import { ApiRequestError, createChatSession, streamSession } from "../api/chatClient";
import { useAuth } from "../auth/webAuth";
import { useLanguage } from "../components/LanguageProvider";
import { isUserVisibleGeneratedDocument, useCases } from "../state/CaseProvider";
import type { CaseCommunicationMode, CaseDocumentRecord, CaseInteraction, CaseRecord, CaseRole } from "../state/CaseProvider";

type AdapterRunOptions = Parameters<ChatModelAdapter["run"]>[0];

const extractTextContent = (content: AdapterRunOptions["messages"][number]["content"]): string => {
  return content
    .map((part) => (part.type === "text" ? part.text : ""))
    .join("\n")
    .trim();
};

const latestUserText = (messages: AdapterRunOptions["messages"]): string => {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message?.role === "user") {
      return extractTextContent(message.content);
    }
  }
  return "";
};

const caseThreadKey = (activeCase: CaseRecord | null): string => {
  if (!activeCase) {
    return "assistant-no-case";
  }
  const historyKey = activeCase.interactionHistory
    .map((interaction) => `${interaction.id}:${interaction.createdAt}`)
    .join("|");
  return `${activeCase.id}:${historyKey}`;
};

const caseInteractionRole = (
  interaction: CaseInteraction,
  t: ReturnType<typeof useLanguage>["t"]
): ThreadMessageLike["role"] => {
  const userActors = new Set([
    "You",
    "You (Voice)",
    "You (Video)",
    t("workspaceUserLabel"),
    t("workspaceUserVoiceLabel"),
    t("workspaceUserVideoLabel")
  ]);
  return userActors.has(interaction.actor) ? "user" : "assistant";
};

const caseInteractionToThreadMessage = (
  interaction: CaseInteraction,
  t: ReturnType<typeof useLanguage>["t"]
): ThreadMessageLike | null => {
  const message = interaction.message.trim();
  if (!message) {
    return null;
  }

  const role = caseInteractionRole(interaction, t);
  const threadMessage: ThreadMessageLike = {
    id: interaction.id,
    role,
    content: message,
    createdAt: new Date(interaction.createdAt),
    metadata: {
      custom: {
        actor: interaction.actor
      }
    }
  };
  if (role === "assistant") {
    return {
      ...threadMessage,
      status: { type: "complete", reason: "stop" }
    };
  }
  return threadMessage;
};

const buildDocumentViewerUrl = ({
  caseId,
  caseTitle,
  document,
  userId
}: {
  caseId: string;
  caseTitle: string;
  document: CaseDocumentRecord;
  userId?: string;
}): string => {
  const params = new URLSearchParams({
    caseId,
    docId: document.id,
    kind: document.kind,
    filename: document.originalFilename,
    caseTitle,
    userId: userId ?? ""
  });
  return `/app/documents/view?${params.toString()}`;
};

const buildGeneratedDocumentsResponseBlock = ({
  caseItem,
  previousDocumentIds,
  userId
}: {
  caseItem: CaseRecord | null;
  previousDocumentIds: Set<string>;
  userId?: string;
}): string => {
  if (!caseItem) {
    return "";
  }
  const newGeneratedDocuments = caseItem.documents.filter(
    (document) => isUserVisibleGeneratedDocument(document) && !previousDocumentIds.has(document.id)
  );
  if (newGeneratedDocuments.length === 0) {
    return "";
  }
  const heading = newGeneratedDocuments.length === 1 ? "Generated document:" : "Generated documents:";
  const links = newGeneratedDocuments.map((document) => {
    const url = buildDocumentViewerUrl({
      caseId: caseItem.id,
      caseTitle: caseItem.title,
      document,
      userId
    });
    return `- [${document.originalFilename}](${url})`;
  });
  return [heading, ...links].join("\n");
};

const appendGeneratedDocumentsResponseBlock = (content: string, block: string): string =>
  block ? `${content.trim()}\n\n${block}`.trim() : content;

const internalDocumentLinkPattern = /\[([^\]]+)]\((\/app\/documents\/view\?[^)\s]+)\)/g;

const AssistantTextPart: React.FC = () => {
  const { text } = useMessagePartText();
  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = internalDocumentLinkPattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    const [, label, href] = match;
    nodes.push(
      <a key={`${href}-${match.index}`} href={href} target="_blank" rel="noreferrer">
        {label}
      </a>
    );
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return <p className="assistant-message__text">{nodes}</p>;
};

const AssistantThread: React.FC = () => {
  const { language, t } = useLanguage();
  const { user } = useAuth();
  const { activeCase, loadCaseData } = useCases();
  const activeCaseId = activeCase?.id;
  const sessionRef = React.useRef<{ language: string; userId?: string; caseId?: string; sessionId: string } | null>(
    null
  );

  const assistantMessages = React.useMemo<ThreadMessageLike[]>(
    () => {
      const caseMessages =
        activeCase?.interactionHistory
          .map((interaction) => caseInteractionToThreadMessage(interaction, t))
          .filter((message): message is ThreadMessageLike => Boolean(message)) ?? [];

      if (caseMessages.length > 0) {
        return caseMessages;
      }

      return [
        {
          role: "assistant",
          content: t("assistantInitialMessage"),
          status: { type: "complete", reason: "stop" }
        }
      ];
    },
    [activeCase?.interactionHistory, t]
  );

  const assistantAdapter = React.useMemo<ChatModelAdapter>(
    () => ({
      async *run(options) {
        const content = latestUserText(options.messages);
        if (!content) {
          yield {
            content: [{ type: "text", text: t("assistantEmptyMessageResponse") }],
            status: { type: "complete", reason: "stop" }
          };
          return;
        }

        try {
          const userId = user?.userId;
          const existingSession = sessionRef.current;
          const session =
            existingSession?.language === language &&
            existingSession.userId === userId &&
            existingSession.caseId === activeCaseId
              ? existingSession
              : {
                  language,
                  userId,
                  caseId: activeCaseId,
                  sessionId: (await createChatSession({ language, userId, caseId: activeCaseId })).id
                };
          sessionRef.current = session;

          let latestAssistantText = "";
          const processingMessages: string[] = [];
          const visibleDocumentIdsBeforeRun = new Set(
            (activeCase?.documents ?? [])
              .filter(isUserVisibleGeneratedDocument)
              .map((document) => document.id)
          );

          for await (const streamEvent of streamSession({
            sessionId: session.sessionId,
            instruction: content,
            signal: options.abortSignal
          })) {
            if (streamEvent.event === "processing" || streamEvent.event === "waiting_for_reply") {
              const message = typeof streamEvent.data.message === "string" ? streamEvent.data.message.trim() : "";
              if (message) {
                processingMessages.push(message);
                yield {
                  content: [{ type: "text", text: processingMessages.join("\n\n") }]
                };
              }
              continue;
            }

            if (streamEvent.event === "message") {
              if (streamEvent.data.role === "assistant") {
                latestAssistantText = streamEvent.data.content;
                yield {
                  content: [{ type: "text", text: latestAssistantText }]
                };
              }
              continue;
            }

            if (streamEvent.event === "error") {
              const detail =
                typeof streamEvent.data.message === "string" ? streamEvent.data.message : "Unknown stream error";
              throw new ApiRequestError("http", detail);
            }
          }

          const refreshedCase =
            activeCaseId && userId ? await loadCaseData(activeCaseId) : null;
          const generatedDocumentsBlock = buildGeneratedDocumentsResponseBlock({
            caseItem: refreshedCase,
            previousDocumentIds: visibleDocumentIdsBeforeRun,
            userId
          });
          const finalAssistantText = appendGeneratedDocumentsResponseBlock(
            latestAssistantText || processingMessages.join("\n\n"),
            generatedDocumentsBlock
          );

          yield {
            content: [{ type: "text", text: finalAssistantText }],
            status: { type: "complete", reason: "stop" }
          };
        } catch (error) {
          const status = error instanceof ApiRequestError && error.status ? String(error.status) : "network";
          const detail = error instanceof Error ? error.message : "Unknown error";
          yield {
            content: [{ type: "text", text: t("assistantApiErrorResponse", { status, detail }) }],
            status: { type: "complete", reason: "stop" }
          };
        }
      }
    }),
    [activeCaseId, language, loadCaseData, t, user?.userId]
  );

  const runtime = useLocalRuntime(assistantAdapter, {
    initialMessages: assistantMessages
  });

  const Message: React.FC = () => (
    <MessagePrimitive.Root className="assistant-message">
      <MessagePrimitive.If user>
        <div className="assistant-message__role">
          <CaseMessageActor fallback={t("assistantUserRole")} />
        </div>
      </MessagePrimitive.If>
      <MessagePrimitive.If assistant>
        <div className="assistant-message__role">
          <CaseMessageActor fallback={t("assistantRole")} />
        </div>
      </MessagePrimitive.If>
      <div className="assistant-message__body">
        <MessagePrimitive.Parts components={{ Text: AssistantTextPart }} />
      </div>
    </MessagePrimitive.Root>
  );

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadPrimitive.Root className="assistant-thread">
        <ThreadPrimitive.Viewport className="assistant-thread__viewport">
          <ThreadPrimitive.Messages components={{ Message }} />
        </ThreadPrimitive.Viewport>
        <ComposerPrimitive.Root className="assistant-composer">
          <ComposerPrimitive.Input
            className="assistant-composer__input"
            placeholder={t("assistantComposerPlaceholder")}
            aria-label={t("assistantComposerLabel")}
          />
          <ComposerPrimitive.Send className="assistant-composer__send" aria-label={t("assistantSend")}>
            <BsArrowUpCircle aria-hidden="true" />
          </ComposerPrimitive.Send>
        </ComposerPrimitive.Root>
      </ThreadPrimitive.Root>
    </AssistantRuntimeProvider>
  );
};

const CaseMessageActor: React.FC<{ fallback: string }> = ({ fallback }) => {
  const actor = useAuiState((state) => {
    const custom = state.message.metadata.custom as Record<string, unknown> | undefined;
    return typeof custom?.actor === "string" ? custom.actor : null;
  });

  return <>{actor ?? fallback}</>;
};

const AssistantConfigurations: React.FC = () => {
  const { t } = useLanguage();
  const { activeCase, setCaseRole, setCaseCommunicationMode } = useCases();

  const communicationModeOptions = React.useMemo(
    () => [
      {
        mode: "Chat" as CaseCommunicationMode,
        label: t("commsChat"),
        icon: <FiMessageSquare aria-hidden="true" />
      },
      {
        mode: "Voice" as CaseCommunicationMode,
        label: t("commsVoice"),
        icon: <FiMic aria-hidden="true" />
      },
      {
        mode: "Video" as CaseCommunicationMode,
        label: t("commsVideo"),
        icon: <FiVideo aria-hidden="true" />
      }
    ],
    [t]
  );

  const roleOptions = React.useMemo(
    () => [
      {
        role: "AI Lawyer" as CaseRole,
        label: t("workspaceLawyerTitle"),
        intent: t("roleIntentLawyer")
      },
      {
        role: "AI Judge" as CaseRole,
        label: t("workspaceJudgeTitle"),
        intent: t("roleIntentJudge")
      },
      {
        role: "Opposing Counsel" as CaseRole,
        label: t("workspaceOpposingTitle"),
        intent: t("roleIntentOpposing")
      }
    ],
    [t]
  );

  return (
    <div className="panel-card assistant-config-card">
      <div className="panel-card__header">
        <h2>{t("workspaceConfigurations")}</h2>
      </div>
      <div className="config-list">
        <fieldset className="role-selector" disabled={!activeCase}>
          <legend>{t("commsTitle")}</legend>
          <p className="hint">{t("commsSubtitle")}</p>
          <div className="segment-control" role="radiogroup">
            {communicationModeOptions.map((option) => {
              const isActive = activeCase?.selectedCommunicationMode === option.mode;
              return (
                <button
                  key={option.mode}
                  type="button"
                  className={`segment-control__option${isActive ? " is-active" : ""}`}
                  aria-pressed={isActive}
                  aria-label={option.label}
                  title={option.label}
                  onClick={() => {
                    if (activeCase) {
                      setCaseCommunicationMode(activeCase.id, option.mode);
                    }
                  }}
                >
                  <span className="segment-control__icon">{option.icon}</span>
                </button>
              );
            })}
          </div>
        </fieldset>

        <fieldset className="role-selector" disabled={!activeCase}>
          <legend>{t("roleSelectorTitle")}</legend>
          <p className="hint">{t("roleSelectorHint")}</p>
          <div className="role-options" role="radiogroup">
            {roleOptions.map((option) => {
              const isActive = activeCase?.selectedRole === option.role;
              return (
                <label
                  key={option.role}
                  className={`role-option${isActive ? " is-active" : ""}`}
                >
                  <input
                    type="radio"
                    name={`assistant-case-role-${activeCase?.id ?? "current"}`}
                    value={option.role}
                    checked={isActive}
                    onChange={() => {
                      if (activeCase) {
                        setCaseRole(activeCase.id, option.role);
                      }
                    }}
                  />
                  <span className="role-option__label">{option.label}</span>
                  <span className="role-option__intent">{option.intent}</span>
                </label>
              );
            })}
          </div>
        </fieldset>
      </div>
    </div>
  );
};

const AssistantWorkspace: React.FC = () => {
  const { t } = useLanguage();
  const { activeCase } = useCases();
  const threadKey = React.useMemo(() => caseThreadKey(activeCase), [activeCase]);

  return (
    <div className="page assistant-workspace-page">
      <section className="assistant-workspace">
        <main className="assistant-main" aria-labelledby="assistant-title">
          <section className="assistant-main__header">
            <div>
              <p className="eyebrow">{t("assistantEyebrow")}</p>
              <h1 id="assistant-title">{t("assistantTitle")}</h1>
              <p>{t("assistantSubtitle")}</p>
            </div>
          </section>

          <AssistantThread key={threadKey} />
        </main>

        <aside className="assistant-tool-panel" aria-label={t("workspaceConfigurations")}>
          <AssistantConfigurations />
        </aside>
      </section>
    </div>
  );
};

export default AssistantWorkspace;
