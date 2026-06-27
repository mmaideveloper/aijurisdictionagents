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
import {
  ApiRequestError,
  chatApiRuntimeConfig,
  createChatSession,
  fetchEffectiveModelRoute,
  streamSession
} from "../api/chatClient";
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
const relativeDocumentLinkPattern = /\[([^\]]+)]\(\s*documents\/[^)\s]+\)/gi;

type AssistantDocumentLink = {
  label: string;
  href: string;
};

type AssistantDocumentPreview = {
  title: string;
  body: string;
};

type AssistantMessagePresentation = {
  conversationalText: string;
  documentPreviews: AssistantDocumentPreview[];
  documentLinks: AssistantDocumentLink[];
};

const separatorLinePattern = /^\s*-{3,}\s*$/;
const internalAudienceLabelPattern = /^\s*(?:USER|USERT)-FACING\s*:\s*/i;
const assistantAgentPrefixPattern = /^\s*(?:LawyerSlovakia|[A-Za-z]+Slovakia)\s*:\s*/;
const documentTitlePattern = /^\s*(?:#{1,4}\s+.+|\*\*(?![^*]{1,80}:\*\*$).+\*\*)\s*$/;

const stripMarkdownHeading = (line: string): string =>
  line
    .trim()
    .replace(/^#{1,4}\s+/, "")
    .replace(/^\*\*(.+)\*\*$/, "$1")
    .trim();

const cleanDocumentLine = (line: string): string =>
  stripMarkdownHeading(line).replace(/\*\*([^*]+)\*\*/g, "$1");

const normalizeVisibleAssistantText = (text: string): string =>
  text
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((line, index) => {
      const withoutAgent = index === 0 ? line.replace(assistantAgentPrefixPattern, "") : line;
      return withoutAgent.replace(internalAudienceLabelPattern, "").trimEnd();
    })
    .join("\n")
    .trim();

const removeInternalDocumentLinks = (text: string): { text: string; links: AssistantDocumentLink[] } => {
  const links: AssistantDocumentLink[] = [];
  const cleaned = text
    .replace(internalDocumentLinkPattern, (_match, label: string, href: string) => {
      links.push({ label, href });
      return "";
    })
    .replace(relativeDocumentLinkPattern, "");
  internalDocumentLinkPattern.lastIndex = 0;
  relativeDocumentLinkPattern.lastIndex = 0;
  return {
    text: cleaned
      .split("\n")
      .filter((line) => {
        const normalized = line.trim().toLowerCase();
        return (
          !/^Generated documents?:\s*$/i.test(normalized) &&
          normalized !== "-" &&
          !normalized.includes("môžete si ho stiahnuť pomocou nasledujúceho odkazu") &&
          !normalized.includes("mozete si ho stiahnut pomocou nasledujuceho odkazu") &&
          !normalized.includes("download using the following link")
        );
      })
      .join("\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim(),
    links
  };
};

const looksLikeDocumentPreview = (chunk: string): boolean => {
  const normalized = chunk.toLowerCase();
  const firstLine = chunk.split("\n").find((line) => line.trim()) ?? "";
  const hasDocumentHeading = documentTitlePattern.test(firstLine.trim());
  const hasLegalBody =
    normalized.includes("podpis") ||
    normalized.includes("signature") ||
    normalized.includes("d\u00e1tum") ||
    normalized.includes("datum") ||
    normalized.includes("i, the undersigned") ||
    normalized.includes("ja, dolu podp\u00edsan");

  return hasDocumentHeading && hasLegalBody && chunk.trim().length > 80;
};

const splitChunkIntoPresentationParts = (chunk: string): { conversational: string[]; documents: string[] } => {
  const lines = chunk.split("\n");
  const documentStartIndexes = lines.reduce<number[]>((indexes, line, index) => {
    if (documentTitlePattern.test(line.trim())) {
      indexes.push(index);
    }
    return indexes;
  }, []);

  if (documentStartIndexes.length === 0) {
    return { conversational: [chunk], documents: [] };
  }

  const conversational: string[] = [];
  const documents: string[] = [];
  const firstDocumentIndex = documentStartIndexes[0] ?? 0;
  const intro = lines.slice(0, firstDocumentIndex).join("\n").trim();
  if (intro) {
    conversational.push(intro);
  }

  documentStartIndexes.forEach((startIndex, index) => {
    const endIndex = documentStartIndexes[index + 1] ?? lines.length;
    const candidate = lines.slice(startIndex, endIndex).join("\n").trim();
    if (looksLikeDocumentPreview(candidate)) {
      documents.push(candidate);
    } else {
      conversational.push(candidate);
    }
  });

  return { conversational, documents };
};

export const parseAssistantMessagePresentation = (text: string): AssistantMessagePresentation => {
  const normalizedText = normalizeVisibleAssistantText(text);
  const { text: textWithoutLinks, links } = removeInternalDocumentLinks(normalizedText);
  if (!textWithoutLinks) {
    return {
      conversationalText: "",
      documentPreviews: [],
      documentLinks: links
    };
  }

  const hasSeparators = textWithoutLinks.split("\n").some((line) => separatorLinePattern.test(line));
  const chunks = textWithoutLinks
    .split(/\n\s*-{3,}\s*\n/g)
    .map((chunk) => chunk.trim())
    .filter(Boolean);
  const conversationalChunks: string[] = [];
  const documentPreviews: AssistantDocumentPreview[] = [];

  chunks.forEach((chunk) => {
    const candidateParts =
      hasSeparators && looksLikeDocumentPreview(chunk)
        ? { conversational: [], documents: [chunk] }
        : splitChunkIntoPresentationParts(chunk);

    conversationalChunks.push(...candidateParts.conversational);
    candidateParts.documents.forEach((documentChunk) => {
      const lines = documentChunk.split("\n");
      const firstContentIndex = lines.findIndex((line) => line.trim());
      const title = stripMarkdownHeading(lines[firstContentIndex] ?? "") || "Document preview";
      const body = lines
        .slice(firstContentIndex + 1)
        .join("\n")
        .trim();

      documentPreviews.push({ title, body });
    });
  });

  return {
    conversationalText: conversationalChunks.join("\n\n").trim(),
    documentPreviews,
    documentLinks: links
  };
};

const renderDocumentBody = (body: string): React.ReactNode[] => {
  const nodes: React.ReactNode[] = [];
  let listItems: string[] = [];

  const flushList = () => {
    if (listItems.length === 0) {
      return;
    }
    nodes.push(
      <ul key={`list-${nodes.length}`} className="assistant-document-preview__list">
        {listItems.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    );
    listItems = [];
  };

  body.split(/\n{2,}/).forEach((block) => {
    const lines = block
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    if (lines.length === 0) {
      return;
    }
    if (lines.every((line) => /^[-*]\s+/.test(line))) {
      listItems.push(...lines.map((line) => line.replace(/^[-*]\s+/, "")));
      return;
    }
    flushList();
    nodes.push(
      <p key={`paragraph-${nodes.length}`} className="assistant-document-preview__paragraph">
        {lines.map(cleanDocumentLine).join(" ")}
      </p>
    );
  });

  flushList();
  return nodes;
};

const AssistantDocumentPreviewCard: React.FC<{ preview: AssistantDocumentPreview; index: number }> = ({
  preview,
  index
}) => (
  <article className="assistant-document-preview" aria-label={`${preview.title} preview`}>
    <div className="assistant-document-preview__sheet">
      <header className="assistant-document-preview__letterhead">
        <span>JurisDigta</span>
        <small>Document preview</small>
      </header>
      <div className="assistant-document-preview__page-marker">A4 preview {index + 1}</div>
      <h3>{preview.title}</h3>
      <div className="assistant-document-preview__content">{renderDocumentBody(preview.body)}</div>
    </div>
  </article>
);

const AssistantDocumentLinks: React.FC<{ links: AssistantDocumentLink[] }> = ({ links }) => {
  if (links.length === 0) {
    return null;
  }

  return (
    <div className="assistant-document-actions" aria-label="Generated documents">
      {links.map((link) => (
        <a key={link.href} className="assistant-document-actions__item" href={link.href} target="_blank" rel="noreferrer">
          <span>Generated PDF</span>
          <strong>{link.label}</strong>
        </a>
      ))}
    </div>
  );
};

const AssistantTextPart: React.FC = () => {
  const { text } = useMessagePartText();
  const presentation = parseAssistantMessagePresentation(text);

  return (
    <>
      {presentation.conversationalText ? (
        <p className="assistant-message__text">{presentation.conversationalText}</p>
      ) : null}
      {presentation.documentPreviews.map((preview, index) => (
        <AssistantDocumentPreviewCard key={`${preview.title}-${index}`} preview={preview} index={index} />
      ))}
      <AssistantDocumentLinks links={presentation.documentLinks} />
    </>
  );
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
  const { user } = useAuth();
  const { activeCase } = useCases();
  const threadKey = React.useMemo(() => caseThreadKey(activeCase), [activeCase]);
  const fallbackModelLabel = React.useMemo(() => chatApiRuntimeConfig().chatModelLabel, []);
  const [modelLabel, setModelLabel] = React.useState(fallbackModelLabel);

  React.useEffect(() => {
    let isCurrent = true;
    void fetchEffectiveModelRoute(user?.userId)
      .then((route) => {
        if (isCurrent && route.label.trim()) {
          setModelLabel(route.label.trim());
        }
      })
      .catch(() => {
        if (isCurrent) {
          setModelLabel(fallbackModelLabel);
        }
      });
    return () => {
      isCurrent = false;
    };
  }, [fallbackModelLabel, user?.userId]);

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
            <div className="assistant-model-disclosure" aria-label={t("assistantModelDisclosureAria")}>
              <span>{t("assistantModelDisclosureLabel")}</span>
              <strong>{modelLabel}</strong>
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
