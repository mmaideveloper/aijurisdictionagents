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
import { FiActivity, FiCopy, FiMessageSquare, FiMic, FiVideo, FiX } from "react-icons/fi";
import {
  ApiRequestError,
  chatApiRuntimeConfig,
  createChatSession,
  fetchEffectiveModelRoute,
  fetchSelectableModelProfiles,
  streamSession
} from "../api/chatClient";
import { createSessionCorrelationId, setActiveSessionCorrelationId } from "../api/correlation";
import { useAuth } from "../auth/webAuth";
import { useLanguage } from "../components/LanguageProvider";
import { AssistantPresentationBlock } from "../components/AssistantPresentationBlock";
import { LegalDocumentPreview } from "../components/LegalDocumentPreview";
import { normalizePresentationBlock, type PresentationBlock } from "../presentation";
import { isUserVisibleGeneratedDocument, useCases } from "../state/CaseProvider";
import type { CaseCitation, CaseCommunicationMode, CaseDocumentRecord, CaseInteraction, CaseRecord, CaseRole } from "../state/CaseProvider";
import { isCaseRoleAvailable } from "../state/caseRoles";
import { AI_ORCHESTRATOR_AGENT_LABEL, normalizeAssistantPresentationText } from "../utils/assistantPresentation";

type AdapterRunOptions = Parameters<ChatModelAdapter["run"]>[0];
const EMPTY_CASE_CITATIONS: CaseCitation[] = [];

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

const citationDisplayLabel = (citation: CaseCitation): string =>
  citation.citationLabel || citation.lawNumber || citation.title;

const citationTypeLabel = (citation: CaseCitation): string => {
  switch (citation.sourceType) {
    case "law":
      return "Law";
    case "court_decision":
      return "Court";
    case "case_document":
      return "Case file";
    case "web":
      return "Web";
    default:
      return "Source";
  }
};

const isFallbackCitation = (citation: CaseCitation): boolean =>
  citation.sourceType === "web" || /AIWebSearchAgent/i.test(citation.retrievalTool ?? "");

const dedupeCaseCitations = (citations: CaseCitation[]): CaseCitation[] => {
  const seen = new Set<string>();
  return citations.filter((citation) => {
    const key = citation.sourceId || citation.sourceUrl || citation.id;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
};

const CitationList: React.FC<{ citations: CaseCitation[]; emptyLabel: string; title?: string }> = ({
  citations,
  emptyLabel,
  title
}) => (
  <section className="citation-list" aria-label={title ?? emptyLabel}>
    {title ? <h3>{title}</h3> : null}
    {citations.length === 0 ? (
      <p className="hint">{emptyLabel}</p>
    ) : (
      <ul>
        {citations.map((citation) => (
          <li key={citation.id} className="citation-list__item">
            <span className="citation-list__type">{citationTypeLabel(citation)}</span>
            {citation.sourceUrl ? (
              <a href={citation.sourceUrl} target="_blank" rel="noreferrer">
                {citationDisplayLabel(citation)}
              </a>
            ) : (
              <strong>{citationDisplayLabel(citation)}</strong>
            )}
            {citation.effectiveFrom ? <span>{citation.effectiveFrom}</span> : null}
            {citation.decisionDate ? <span>{citation.decisionDate}</span> : null}
            {citation.retrievalTool ? <span>{citation.retrievalTool}</span> : null}
            {isFallbackCitation(citation) ? (
              <p className="citation-list__warning">
                Warning: this source came from official web-search fallback, not from JurisDigta system vector DB. Human legal review is required.
              </p>
            ) : null}
            {citation.snippet ? <p>{citation.snippet}</p> : null}
          </li>
        ))}
      </ul>
    )}
  </section>
);

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
        actor: interaction.actor,
        citations: interaction.citations,
        presentation: interaction.presentation
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

const appendGeneratedDocumentsResponseBlock = (content: string, block: string): string => {
  if (!block || content.includes("/app/documents/view?")) {
    return content;
  }
  return `${content.trim()}\n\n${block}`.trim();
};

const localizeApiErrorDetail = (
  error: unknown,
  t: ReturnType<typeof useLanguage>["t"]
): string => {
  if (error instanceof ApiRequestError && error.code === "case_write_window_expired") {
    return t("assistantCaseWriteWindowExpiredDetail", {
      plan: String(error.params?.plan ?? "Free"),
      days: String(error.params?.days ?? "1")
    });
  }
  if (error instanceof ApiRequestError && error.code === "local_model_timeout") {
    return t("assistantLocalModelTimeout");
  }
  if (error instanceof ApiRequestError && error.code === "external_model_timeout") {
    return t("assistantExternalModelTimeout");
  }

  return error instanceof Error ? error.message : "Unknown error";
};

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
const documentRootTitlePattern = /(?:splnomocnen|power of attorney|potvrden|zmluv|agreement|contract|dohod|v[ýy]zv|zalob|žalob|n[áa]vrh|memorand)/i;
const conversationBoundaryTitlePattern = /^(?:čo ďalej|co dalej|what next|next steps|wie weiter)\??$/i;

const stripMarkdownHeading = (line: string): string =>
  line
    .trim()
    .replace(/^#{1,4}\s+/, "")
    .replace(/^\*\*(.+)\*\*$/, "$1")
    .trim();

const isDocumentRootTitle = (line: string): boolean => {
  if (!documentTitlePattern.test(line.trim())) {
    return false;
  }
  const title = stripMarkdownHeading(line).replace(/^\d+[.)]?\s+/, "").trim();
  return !/^\d+[.)]?\s+/.test(stripMarkdownHeading(line)) && documentRootTitlePattern.test(title);
};

const isConversationBoundaryTitle = (line: string): boolean =>
  documentTitlePattern.test(line.trim()) && conversationBoundaryTitlePattern.test(stripMarkdownHeading(line));

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

  const lines = textWithoutLinks.split("\n");
  const rootIndexes = lines.reduce<number[]>((indexes, line, index) => {
    if (isDocumentRootTitle(line)) {
      indexes.push(index);
    }
    return indexes;
  }, []);
  if (rootIndexes.length > 0) {
    const documentPreviews: AssistantDocumentPreview[] = [];
    const documentLineIndexes = new Set<number>();
    rootIndexes.forEach((startIndex, rootIndex) => {
      const nextRootIndex = rootIndexes[rootIndex + 1] ?? lines.length;
      let endIndex = nextRootIndex;
      for (let index = startIndex + 1; index < nextRootIndex; index += 1) {
        if (isConversationBoundaryTitle(lines[index] ?? "")) {
          endIndex = index;
          break;
        }
      }
      for (let index = startIndex; index < endIndex; index += 1) {
        documentLineIndexes.add(index);
      }
      const body = lines.slice(startIndex + 1, endIndex).join("\n").trim();
      if (looksLikeDocumentPreview(`${lines[startIndex]}\n${body}`)) {
        documentPreviews.push({ title: stripMarkdownHeading(lines[startIndex] ?? ""), body });
      }
    });
    if (documentPreviews.length > 0) {
      const conversationalText = lines
        .filter((_line, index) => !documentLineIndexes.has(index))
        .filter((line) => !separatorLinePattern.test(line))
        .join("\n")
        .replace(/\n{3,}/g, "\n\n")
        .trim();
      return { conversationalText, documentPreviews, documentLinks: links };
    }
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

const AssistantDocumentPreviewCard: React.FC<{ preview: AssistantDocumentPreview; index: number }> = ({
  preview,
  index
}) => {
  const { t } = useLanguage();
  return (
    <LegalDocumentPreview
      title={preview.title}
      body={preview.body}
      previewLabel={t("assistantDocumentPreviewLabel")}
      pageLabel={t("assistantDocumentPreviewPage", { number: index + 1 })}
    />
  );
};

const AssistantDocumentLinks: React.FC<{ links: AssistantDocumentLink[] }> = ({ links }) => {
  const { t } = useLanguage();
  if (links.length === 0) {
    return null;
  }

  return (
    <div className="assistant-document-actions" aria-label="Generated documents">
      {links.map((link) => (
        <a key={link.href} className="assistant-document-actions__item" href={link.href} target="_blank" rel="noreferrer">
          <span>{t("assistantGeneratedPdf")}</span>
          <strong>{link.label}</strong>
        </a>
      ))}
    </div>
  );
};

const AssistantTextPart: React.FC = () => {
  const { text } = useMessagePartText();
  const typedPresentation = useAuiState((state) => {
    const custom = state.message.metadata.custom as Record<string, unknown> | undefined;
    return normalizePresentationBlock(custom?.presentation);
  });
  const presentation = parseAssistantMessagePresentation(normalizeAssistantPresentationText(text));
  const conversationalText = presentation.conversationalText
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1");

  return (
    <>
      {typedPresentation ? (
        <AssistantPresentationBlock block={typedPresentation} />
      ) : conversationalText ? (
        <p className="assistant-message__text">{conversationalText}</p>
      ) : null}
      {!typedPresentation
        ? presentation.documentPreviews.map((preview, index) => (
            <AssistantDocumentPreviewCard key={`${preview.title}-${index}`} preview={preview} index={index} />
          ))
        : null}
      <AssistantDocumentLinks links={presentation.documentLinks} />
    </>
  );
};

const userInteractionActors = new Set(["You", "You (Voice)", "You (Video)"]);

const isAssistantInteraction = (interaction: CaseInteraction): boolean =>
  !userInteractionActors.has(interaction.actor) && interaction.actor !== "System";

const findLatestAssistantInteraction = (caseItem: CaseRecord | null): CaseInteraction | null => {
  if (!caseItem) {
    return null;
  }
  for (let index = caseItem.interactionHistory.length - 1; index >= 0; index -= 1) {
    const interaction = caseItem.interactionHistory[index];
    if (interaction && isAssistantInteraction(interaction)) {
      return interaction;
    }
  }
  return null;
};

const progressOnlyAssistantPattern = /teraz\s+vytvor[ií]m\s+pdf\s+dokument|chv[ií][ľl]u\s+pros[ií]m|creating\s+(?:the\s+)?pdf/i;

const shouldPreferHydratedAssistantMessage = (currentText: string, hydratedText: string): boolean => {
  if (!hydratedText.trim() || hydratedText.trim() === currentText.trim()) {
    return false;
  }
  const presentation = parseAssistantMessagePresentation(hydratedText);
  return (
    progressOnlyAssistantPattern.test(currentText) ||
    presentation.documentPreviews.length > 0 ||
    presentation.documentLinks.length > 0
  );
};

const isUserVisibleProcessingEvent = (data: Record<string, unknown>): boolean => {
  const details = data.details;
  return (
    typeof details === "object" &&
    details !== null &&
    "user_visible" in details &&
    (details as { user_visible?: unknown }).user_visible === true
  );
};

const prependUserVisibleProcessingMessages = (content: string, messages: string[]): string => {
  const uniqueMessages = messages.filter((message, index) => messages.indexOf(message) === index);
  if (uniqueMessages.length === 0) {
    return content;
  }
  const body = content.trim();
  return body ? `${uniqueMessages.join("\n\n")}\n\n${body}` : uniqueMessages.join("\n\n");
};

const currentCaseDeepLinkId = (): string | undefined => {
  if (typeof window === "undefined") {
    return undefined;
  }
  const match = window.location.pathname.match(/^\/case\/([^/?#]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : undefined;
};

const AssistantThread: React.FC<{
  selectedModelProfileId?: string;
  onCorrelationIdChange: (correlationId: string) => void;
}> = ({ selectedModelProfileId, onCorrelationIdChange }) => {
  const { language, t } = useLanguage();
  const { isAuthenticated, isAuthLoading, user } = useAuth();
  const { activeCase, loadCaseData } = useCases();
  const activeCaseId = activeCase?.id;
  const sessionRef = React.useRef<{ language: string; userId?: string; caseId?: string; sessionId: string; correlationId: string } | null>(
    null
  );
  React.useEffect(
    () => () => {
      setActiveSessionCorrelationId("");
      onCorrelationIdChange("");
    },
    [onCorrelationIdChange]
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
          if (isAuthenticated && (isAuthLoading || !userId)) {
            yield {
              content: [{ type: "text", text: t("assistantAuthLoadingResponse") }],
              status: { type: "complete", reason: "stop" }
            };
            return;
          }

          const existingSession = sessionRef.current;
          const session =
            existingSession?.language === language &&
            existingSession.userId === userId &&
            existingSession.caseId === activeCaseId
              ? existingSession
              : await (async () => {
                  const requestedCorrelationId = createSessionCorrelationId();
                  const created = await createChatSession({
                    language,
                    userId,
                    caseId: activeCaseId,
                    modelProfileId: selectedModelProfileId,
                    correlationId: requestedCorrelationId
                  });
                  return {
                    language,
                    userId,
                    caseId: activeCaseId,
                    sessionId: created.id,
                    correlationId: created.correlation_id || requestedCorrelationId
                  };
                })();
          sessionRef.current = session;
          onCorrelationIdChange(session.correlationId);

          let latestAssistantText = "";
          let latestPresentation: PresentationBlock | null = null;
          const processingMessages: string[] = [];
          const userVisibleProcessingMessages: string[] = [];
          let activeProgressMessage = "";
          const visibleDocumentIdsBeforeRun = new Set(
            (activeCase?.documents ?? [])
              .filter(isUserVisibleGeneratedDocument)
              .map((document) => document.id)
          );

          for await (const streamEvent of streamSession({
            sessionId: session.sessionId,
            instruction: content,
            userId,
            userEmail: user?.email,
            modelProfileId: selectedModelProfileId,
            signal: options.abortSignal,
            correlationId: session.correlationId
          })) {
            if (streamEvent.event === "processing" || streamEvent.event === "waiting_for_reply") {
              const message = typeof streamEvent.data.message === "string" ? streamEvent.data.message.trim() : "";
              if (message) {
                const isStillWorking =
                  "stage" in streamEvent.data && streamEvent.data.stage === "still_working";
                if (isStillWorking) {
                  activeProgressMessage = message;
                } else if (processingMessages.at(-1) !== message) {
                  processingMessages.push(message);
                }
                if (!isStillWorking && isUserVisibleProcessingEvent(streamEvent.data)) {
                  userVisibleProcessingMessages.push(message);
                }
                const visibleMessages = [...processingMessages, activeProgressMessage].filter(Boolean);
                yield {
                  content: [{ type: "text", text: visibleMessages.join("\n\n") }]
                };
              }
              continue;
            }

            if (streamEvent.event === "message") {
              if (streamEvent.data.role === "assistant") {
                activeProgressMessage = "";
                latestAssistantText = streamEvent.data.content;
                latestPresentation = normalizePresentationBlock(streamEvent.data.presentation);
                yield {
                  content: [{ type: "text", text: latestAssistantText }],
                  metadata: { custom: { presentation: latestPresentation } }
                };
              }
              continue;
            }

            if (streamEvent.event === "error") {
              const detail =
                typeof streamEvent.data.message === "string" ? streamEvent.data.message : "Unknown stream error";
              const code = typeof streamEvent.data.code === "string" ? streamEvent.data.code : undefined;
              const params =
                typeof streamEvent.data.params === "object" && streamEvent.data.params !== null
                  ? (streamEvent.data.params as Record<string, string | number | boolean | null | undefined>)
                  : undefined;
              throw new ApiRequestError("http", detail, undefined, { code, params });
            }
          }

          const refreshedCase =
            activeCaseId && userId ? await loadCaseData(activeCaseId) : null;
          const generatedDocumentsBlock = buildGeneratedDocumentsResponseBlock({
            caseItem: refreshedCase,
            previousDocumentIds: visibleDocumentIdsBeforeRun,
            userId
          });
          const hydratedAssistantInteraction = findLatestAssistantInteraction(refreshedCase);
          const hydratedAssistantMessage = hydratedAssistantInteraction?.message ?? "";
          const hydratedPresentation = hydratedAssistantInteraction?.presentation ?? null;
          const streamedAssistantText = latestAssistantText || processingMessages.join("\n\n");
          const responseSourceText = shouldPreferHydratedAssistantMessage(
            streamedAssistantText,
            hydratedAssistantMessage
          )
            ? hydratedAssistantMessage
            : streamedAssistantText;
          const finalAssistantText = appendGeneratedDocumentsResponseBlock(
            prependUserVisibleProcessingMessages(responseSourceText, userVisibleProcessingMessages),
            generatedDocumentsBlock
          );

          yield {
            content: [{ type: "text", text: finalAssistantText }],
            metadata: {
              custom: {
                presentation: hydratedPresentation ?? latestPresentation
              }
            },
            status: { type: "complete", reason: "stop" }
          };
        } catch (error) {
          const detail = localizeApiErrorDetail(error, t);
          const isModelTimeout =
            error instanceof ApiRequestError &&
            (error.code === "local_model_timeout" || error.code === "external_model_timeout");
          const status =
            error instanceof ApiRequestError && error.kind === "network"
              ? "network"
              : error instanceof ApiRequestError && error.status
                ? String(error.status)
                : "stream";
          yield {
            content: [
              {
                type: "text",
                text: isModelTimeout ? detail : t("assistantApiErrorResponse", { status, detail })
              }
            ],
            status: { type: "complete", reason: "stop" }
          };
        }
      }
    }),
    [
      activeCase?.documents,
      activeCaseId,
      isAuthenticated,
      isAuthLoading,
      language,
      loadCaseData,
      onCorrelationIdChange,
      selectedModelProfileId,
      t,
      user?.email,
      user?.userId
    ]
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
        <CaseMessageCitations />
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

  if (actor && /^LangGraph(?:[A-Za-z0-9_.:-]*)?$/i.test(actor.trim())) {
    return <>{AI_ORCHESTRATOR_AGENT_LABEL}</>;
  }
  const isInternalActor = actor !== null && /^(?:LawyerSlovakia|[A-Za-z]+Slovakia|AI Lawyer|You(?: \(.+\))?)$/i.test(actor);
  return <>{actor && !isInternalActor ? actor : fallback}</>;
};

const CaseMessageCitations: React.FC = () => {
  const { t } = useLanguage();
  const citations = useAuiState((state) => {
    const custom = state.message.metadata.custom as Record<string, unknown> | undefined;
    return Array.isArray(custom?.citations) ? (custom.citations as CaseCitation[]) : EMPTY_CASE_CITATIONS;
  }) ?? EMPTY_CASE_CITATIONS;
  if (citations.length === 0) {
    return null;
  }
  return <CitationList citations={citations} emptyLabel={t("workspaceCitationsEmpty")} />;
};

const DiagnosticsDialog: React.FC<{ correlationId: string; onClose: () => void }> = ({
  correlationId,
  onClose
}) => {
  const { t } = useLanguage();
  const closeButtonRef = React.useRef<HTMLButtonElement>(null);
  const [copyStatus, setCopyStatus] = React.useState<"idle" | "copied" | "failed">("idle");
  const resolvedCorrelationId = correlationId.trim();

  React.useEffect(() => {
    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const copyCorrelationId = async () => {
    if (!resolvedCorrelationId) {
      return;
    }
    try {
      await navigator.clipboard.writeText(resolvedCorrelationId);
      setCopyStatus("copied");
    } catch {
      setCopyStatus("failed");
    }
  };

  return (
    <div className="diagnostics-dialog-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) {
        onClose();
      }
    }}>
      <section
        className="diagnostics-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="diagnostics-dialog-title"
        aria-describedby="diagnostics-dialog-description"
      >
        <div className="diagnostics-dialog__header">
          <div>
            <p className="eyebrow">{t("diagnosticsEyebrow")}</p>
            <h2 id="diagnostics-dialog-title">{t("diagnosticsTitle")}</h2>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            className="diagnostics-dialog__close"
            aria-label={t("diagnosticsClose")}
            onClick={onClose}
          >
            <FiX aria-hidden="true" />
          </button>
        </div>
        <p id="diagnostics-dialog-description">{t("diagnosticsDescription")}</p>
        <div className="diagnostics-id-field">
          <span>{t("assistantCorrelationId")}</span>
          <code>{resolvedCorrelationId || t("diagnosticsUnavailableValue")}</code>
        </div>
        {!resolvedCorrelationId ? <p className="diagnostics-dialog__notice">{t("diagnosticsUnavailableHint")}</p> : null}
        <div className="diagnostics-dialog__actions">
          <button
            type="button"
            className="button primary"
            disabled={!resolvedCorrelationId}
            onClick={() => void copyCorrelationId()}
          >
            <FiCopy aria-hidden="true" />
            {t("assistantCopyCorrelationId")}
          </button>
        </div>
        <p className="diagnostics-dialog__copy-status" role="status" aria-live="polite">
          {copyStatus === "copied"
            ? t("diagnosticsCopySuccess")
            : copyStatus === "failed"
              ? t("diagnosticsCopyFailed")
              : ""}
        </p>
        <p className="diagnostics-dialog__privacy">{t("diagnosticsPrivacyNotice")}</p>
      </section>
    </div>
  );
};

const AssistantConfigurations: React.FC<{ correlationId: string }> = ({ correlationId }) => {
  const { t } = useLanguage();
  const { activeCase, setCaseRole, setCaseCommunicationMode } = useCases();
  const [isDiagnosticsOpen, setIsDiagnosticsOpen] = React.useState(false);
  const diagnosticsButtonRef = React.useRef<HTMLButtonElement>(null);
  const closeDiagnostics = React.useCallback(() => {
    setIsDiagnosticsOpen(false);
    window.setTimeout(() => diagnosticsButtonRef.current?.focus(), 0);
  }, []);

  const communicationModeOptions = React.useMemo(
    () => [
      {
        mode: "Chat" as CaseCommunicationMode,
        label: t("commsChat"),
        icon: <FiMessageSquare aria-hidden="true" />,
        disabled: false
      },
      {
        mode: "Voice" as CaseCommunicationMode,
        label: t("commsVoice"),
        icon: <FiMic aria-hidden="true" />,
        disabled: true
      },
      {
        mode: "Video" as CaseCommunicationMode,
        label: t("commsVideo"),
        icon: <FiVideo aria-hidden="true" />,
        disabled: true
      }
    ],
    [t]
  );

  React.useEffect(() => {
    if (activeCase && activeCase.selectedCommunicationMode !== "Chat") {
      setCaseCommunicationMode(activeCase.id, "Chat");
    }
  }, [activeCase, setCaseCommunicationMode]);

  const roleOptions = React.useMemo(
    () => [
      {
        role: "AI Lawyer" as CaseRole,
        label: t("workspaceLawyerTitle"),
        intent: t("roleIntentLawyer"),
        disabled: false
      },
      {
        role: "AI Judge" as CaseRole,
        label: t("workspaceJudgeTitle"),
        intent: t("roleIntentJudge"),
        disabled: true
      },
      {
        role: "Opposing Counsel" as CaseRole,
        label: t("workspaceOpposingTitle"),
        intent: t("roleIntentOpposing"),
        disabled: true
      }
    ],
    [t]
  );

  return (
    <div className="panel-card assistant-config-card">
      <div className="panel-card__header">
        <h2>{t("workspaceConfigurations")}</h2>
        <button
          ref={diagnosticsButtonRef}
          type="button"
          className="assistant-diagnostics-button"
          aria-label={t("diagnosticsOpen")}
          title={t("diagnosticsOpen")}
          onClick={() => setIsDiagnosticsOpen(true)}
        >
          <FiActivity aria-hidden="true" />
          <span>{t("diagnosticsButton")}</span>
        </button>
      </div>
      <div className="config-list">
        <fieldset className="role-selector" disabled={!activeCase}>
          <legend>{t("commsTitle")}</legend>
          <p className="hint">{t("commsSubtitle")}</p>
          <div className="segment-control" role="radiogroup">
            {communicationModeOptions.map((option) => {
              const isDisabled = option.disabled || !activeCase;
              const isActive = !isDisabled && activeCase?.selectedCommunicationMode === option.mode;
              return (
                <button
                  key={option.mode}
                  type="button"
                  className={`segment-control__option${isActive ? " is-active" : ""}${isDisabled ? " is-disabled" : ""}`}
                  aria-pressed={isActive}
                  aria-label={option.label}
                  aria-disabled={isDisabled}
                  tabIndex={isDisabled ? -1 : undefined}
                  title={option.disabled ? t("roleUnavailable") : option.label}
                  data-tooltip={option.disabled ? t("roleUnavailable") : undefined}
                  onClick={() => {
                    if (activeCase && !isDisabled) {
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
              const isDisabled = option.disabled || !isCaseRoleAvailable(option.role);
              const isActive = !isDisabled && activeCase?.selectedRole === option.role;
              return (
                <label
                  key={option.role}
                  className={`role-option${isActive ? " is-active" : ""}${isDisabled ? " is-disabled" : ""}`}
                  aria-disabled={isDisabled}
                  title={isDisabled ? t("roleUnavailable") : undefined}
                >
                  <input
                    type="radio"
                    name={`assistant-case-role-${activeCase?.id ?? "current"}`}
                    value={option.role}
                    checked={isActive}
                    disabled={isDisabled}
                    onChange={() => {
                      if (activeCase && !isDisabled) {
                        setCaseRole(activeCase.id, option.role);
                      }
                    }}
                  />
                  <span className="role-option__label">{option.label}</span>
                  <span className="role-option__intent">{option.intent}</span>
                  {isDisabled ? <span className="role-option__status">{t("roleUnavailable")}</span> : null}
                </label>
              );
            })}
          </div>
        </fieldset>
        <CitationList
          title={t("workspaceCitationsTitle")}
          citations={dedupeCaseCitations(activeCase?.citations ?? [])}
          emptyLabel={t("workspaceCitationsEmpty")}
        />
      </div>
      {isDiagnosticsOpen ? (
        <DiagnosticsDialog correlationId={correlationId} onClose={closeDiagnostics} />
      ) : null}
    </div>
  );
};

const AssistantWorkspace: React.FC = () => {
  const { t } = useLanguage();
  const { isAuthenticated, isAuthLoading, user } = useAuth();
  const caseState = useCases();
  const {
    activeCase,
    cases = [],
    isLoadingCases = false,
    selectCase = () => undefined
  } = caseState;
  const routeCaseId = currentCaseDeepLinkId();
  const threadKey = React.useMemo(() => caseThreadKey(activeCase), [activeCase]);
  const fallbackModelLabel = React.useMemo(() => chatApiRuntimeConfig().chatModelLabel, []);
  const pendingModelLabel = t("assistantModelDisclosurePending");
  const [modelLabel, setModelLabel] = React.useState(
    isAuthenticated ? pendingModelLabel : fallbackModelLabel
  );
  const [selectedModelProfileId, setSelectedModelProfileId] = React.useState("");
  const [correlationId, setCorrelationId] = React.useState("");
  const handleCorrelationIdChange = React.useCallback((nextCorrelationId: string) => {
    setCorrelationId(nextCorrelationId);
  }, []);
  const [selectableProfiles, setSelectableProfiles] = React.useState<
    { model_profile_id: string; label: string; is_external: boolean; is_local: boolean }[]
  >([]);

  React.useEffect(() => {
    if (isAuthenticated && !user?.userId) {
      setModelLabel(pendingModelLabel);
      return;
    }

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
  }, [fallbackModelLabel, isAuthenticated, isAuthLoading, pendingModelLabel, user?.userId]);

  React.useEffect(() => {
    const userId = user?.userId?.trim();
    const userEmail = user?.email?.trim();
    if (!isAuthenticated || (!userId && !userEmail)) {
      setSelectableProfiles([]);
      setSelectedModelProfileId("");
      return;
    }

    let isCurrent = true;
    void fetchSelectableModelProfiles({ userId, userEmail })
      .then((response) => {
        if (isCurrent) {
          setSelectableProfiles(response.eligible ? response.profiles : []);
        }
      })
      .catch(() => {
        if (isCurrent) {
          setSelectableProfiles([]);
        }
      });
    return () => {
      isCurrent = false;
    };
  }, [isAuthenticated, user?.email, user?.userId]);

  React.useEffect(() => {
    setSelectedModelProfileId("");
  }, [activeCase?.id]);

  React.useEffect(() => {
    const requestedCaseId = routeCaseId?.trim();
    if (!requestedCaseId || isLoadingCases || activeCase?.id === requestedCaseId) {
      return;
    }
    if (cases.some((caseItem) => caseItem.id === requestedCaseId)) {
      selectCase(requestedCaseId);
    }
  }, [activeCase?.id, cases, isLoadingCases, routeCaseId, selectCase]);

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
              {selectableProfiles.length > 0 ? (
                <select
                  aria-label={t("assistantModelSelectorLabel")}
                  value={selectedModelProfileId}
                  onChange={(event) => setSelectedModelProfileId(event.currentTarget.value)}
                >
                  <option value="">{modelLabel}</option>
                  {selectableProfiles.map((profile) => (
                    <option key={profile.model_profile_id} value={profile.model_profile_id}>
                      {profile.label}
                    </option>
                  ))}
                </select>
              ) : (
                <strong>{modelLabel}</strong>
              )}
            </div>
          </section>

          <AssistantThread
            key={threadKey}
            selectedModelProfileId={selectedModelProfileId || undefined}
            onCorrelationIdChange={handleCorrelationIdChange}
          />
        </main>

        <aside className="assistant-tool-panel" aria-label={t("workspaceConfigurations")}>
          <AssistantConfigurations correlationId={correlationId} />
        </aside>
      </section>
    </div>
  );
};

export default AssistantWorkspace;
