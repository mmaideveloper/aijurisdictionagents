import React from "react";
import {
  createApiCase,
  deleteApiCase,
  deleteApiCaseDocument,
  getCaseHistory,
  listCases,
  uploadApiCaseDocuments,
  type ApiCase,
  type ApiCaseCitation,
  type ApiCaseDocument,
  type ApiCaseHistoryMessage
} from "../api/caseClient";
import { createChatSession, replyToSession } from "../api/chatClient";
import { useAuth } from "../auth/webAuth";
import { getMockCaseTemplate, isSeededCaseTemplateId } from "../content/mockCaseTemplates";
import { translate, type Language, type TranslationKey, type TranslationValues } from "../data/translations";
import { consoleLogger } from "../logging/consoleLogger";
import { assistantAgentDisplayName, normalizeAssistantPresentationText } from "../utils/assistantPresentation";
import { useLanguage } from "../components/LanguageProvider";
import { normalizeCaseRole, type CaseRole } from "./caseRoles";

export type { CaseRole } from "./caseRoles";

export type CaseStatus = "In progress" | "On hold" | "Scheduled" | "Completed";
export type CaseMode = "Draft" | "Review" | "Live" | "Archive";
export type CaseCommunicationMode = "Chat" | "Voice" | "Video";

export type SendCaseMessageInput = {
  caseId: string;
  content: string;
  communicationMode: CaseCommunicationMode;
};

export type SendCaseMessageResult = {
  sessionId: string;
  assistantActor: string;
  assistantMessage: string;
};

export type CaseInteraction = {
  id: string;
  createdAt: string;
  actor: string;
  message: string;
  citations: CaseCitation[];
};

export type CaseCitation = {
  id: string;
  caseId: string;
  questionMessageId: string | null;
  answerMessageId: string | null;
  sourceType: "law" | "court_decision" | "case_document" | "web" | "other";
  sourceId: string | null;
  sourceUrl: string | null;
  title: string;
  citationLabel: string | null;
  lawNumber: string | null;
  section: string | null;
  effectiveFrom: string | null;
  court: string | null;
  ecli: string | null;
  fileNumber: string | null;
  decisionDate: string | null;
  snippet: string | null;
  retrievalTool: string | null;
  relevanceScore: number | null;
  createdAt: string;
};

export type CaseWorkspace = {
  meta: string;
  objective: string;
  nextAction: string;
  jurisdiction: string;
  output: string;
};

export type CaseDocumentRecord = {
  id: string;
  caseId: string;
  kind: string;
  originalFilename: string;
  mimeType: string;
  size: number;
  sizeLabel: string;
  uploadedAt: string;
};

export type CaseDocumentSummary = CaseDocumentRecord & {
  caseTitle: string;
};

export type CreateCaseDocumentInput = {
  originalFilename: string;
  mimeType: string;
  size: number;
  file?: File;
};

export type CreateCaseInput = {
  title: string;
  jurisdiction: string;
  opposingParty: string;
  documents: CreateCaseDocumentInput[];
};

export type CaseRecord = {
  id: string;
  title: string;
  description: string;
  status: CaseStatus;
  createdAt: string;
  interactionHistory: CaseInteraction[];
  selectedRole: CaseRole;
  selectedMode: CaseMode;
  selectedCommunicationMode: CaseCommunicationMode;
  workspace: CaseWorkspace;
  jurisdiction: string;
  opposingParty: string;
  documents: CaseDocumentRecord[];
  citations: CaseCitation[];
  source: "api" | "mock";
};

type CaseContextValue = {
  cases: CaseRecord[];
  documents: CaseDocumentSummary[];
  activeCaseId: string | null;
  activeCase: CaseRecord | null;
  hasSelectedCase: boolean;
  continueRequested: boolean;
  isLoadingCases: boolean;
  caseLoadError: string | null;
  createCase: (input: CreateCaseInput) => Promise<CaseRecord>;
  deleteCase: (caseId: string) => Promise<void>;
  deleteDocument: (caseId: string, docId: string) => Promise<void>;
  loadCaseData: (caseId: string) => Promise<CaseRecord | null>;
  setActiveCase: (caseId: string) => void;
  selectCase: (caseId: string) => void;
  setContinueRequested: (value: boolean) => void;
  addInteraction: (caseId: string, actor: string, message: string) => void;
  sendCaseMessage: (input: SendCaseMessageInput) => Promise<SendCaseMessageResult>;
  updateCase: (caseId: string, update: Partial<CaseRecord>) => void;
  setCaseRole: (caseId: string, role: CaseRole) => void;
  setCaseMode: (caseId: string, mode: CaseMode) => void;
  setCaseCommunicationMode: (caseId: string, mode: CaseCommunicationMode) => void;
};

const CaseContext = React.createContext<CaseContextValue | undefined>(undefined);
const CASE_STORAGE_KEY = "aijurisdictionfrontend.mock.cases.v1";
const STORED_DOCUMENT_MESSAGE_PATTERN = /^Stored (?<count>\d+) uploaded documents? in mock profile storage\.$/;
const DOCUMENT_DELETED_MESSAGE_PATTERN = /^Document deleted at (?<deletedAt>.+)\.$/;
const LOCALIZED_INTERACTION_PREFIX = "__aj_i18n__:";

type LocalizedInteractionDescriptor = {
  key: TranslationKey;
  values?: TranslationValues;
};

type CaseSessionCacheRecord = {
  language: Language;
  sessionId: string;
};

const USER_VISIBLE_GENERATED_DOCUMENT_KINDS = new Set(["generated_document"]);

export const isUserVisibleGeneratedDocument = (document: Pick<CaseDocumentRecord, "kind" | "originalFilename">): boolean => {
  if (!USER_VISIBLE_GENERATED_DOCUMENT_KINDS.has(document.kind)) {
    return false;
  }
  const normalizedName = document.originalFilename.trim().toLowerCase();
  return !(
    normalizedName.startsWith("assistant-technical-") ||
    normalizedName.startsWith("session-") ||
    normalizedName.startsWith("spracovanie-stale-prebieha") ||
    normalizedName.includes("technical") ||
    normalizedName.includes("payload")
  );
};

export const buildLocalizedInteractionMessage = (
  key: TranslationKey,
  values?: TranslationValues
): string => {
  const descriptor: LocalizedInteractionDescriptor = values ? { key, values } : { key };
  return `${LOCALIZED_INTERACTION_PREFIX}${JSON.stringify(descriptor)}`;
};

const parseLocalizedInteractionMessage = (
  message: string
): LocalizedInteractionDescriptor | null => {
  if (!message.startsWith(LOCALIZED_INTERACTION_PREFIX)) {
    return null;
  }

  const payload = message.slice(LOCALIZED_INTERACTION_PREFIX.length);
  try {
    const parsed = JSON.parse(payload) as Partial<LocalizedInteractionDescriptor>;
    if (!parsed || typeof parsed.key !== "string") {
      return null;
    }
    return parsed as LocalizedInteractionDescriptor;
  } catch {
    return null;
  }
};

const USER_INTERACTION_ACTORS = ["You", "You (Voice)", "You (Video)"] as const;
const ROLE_INTERACTION_ACTORS = ["AI Lawyer", "AI Judge", "Opposing Counsel"] as const;

const isUserInteractionActor = (actor: string): boolean =>
  USER_INTERACTION_ACTORS.includes(actor as (typeof USER_INTERACTION_ACTORS)[number]);

const isSeededAssistantIntroInteraction = (interaction: CaseInteraction): boolean => {
  if (!ROLE_INTERACTION_ACTORS.includes(interaction.actor as (typeof ROLE_INTERACTION_ACTORS)[number])) {
    return false;
  }

  const localizedDescriptor = parseLocalizedInteractionMessage(interaction.message);
  return localizedDescriptor?.key === "mockCreatedCaseOpenMessage";
};

const stripSeededAssistantIntro = (interactionHistory: CaseInteraction[]): CaseInteraction[] =>
  interactionHistory.filter((interaction) => !isSeededAssistantIntroInteraction(interaction));

const normalizeInteractionHistory = (interactionHistory: CaseInteraction[]): CaseInteraction[] => {
  const hasUserInteraction = interactionHistory.some((interaction) =>
    isUserInteractionActor(interaction.actor)
  );

  if (!hasUserInteraction) {
    return interactionHistory;
  }

  return stripSeededAssistantIntro(interactionHistory);
};

const buildCreatedCaseDescription = (jurisdiction: string, opposingParty: string, language: Language) =>
  translate(language, "mockCreatedCaseDescription", {
    jurisdiction,
    opposingParty
  });

const buildCreatedCaseMeta = (jurisdiction: string, documentCount: number, language: Language) =>
  translate(
    language,
    documentCount === 1 ? "mockCreatedCaseMetaSingular" : "mockCreatedCaseMetaPlural",
    {
      jurisdiction,
      count: documentCount
    }
  );

const localizeInteractionActor = (
  actor: string,
  language: Language
): string => {
  if (actor === "AI Lawyer") {
    return translate(language, "workspaceLawyerTitle");
  }
  if (actor === "AI Judge") {
    return translate(language, "workspaceJudgeTitle");
  }
  if (actor === "Opposing Counsel") {
    return translate(language, "workspaceOpposingTitle");
  }
  if (actor === "System") {
    return translate(language, "workspaceSystemLabel");
  }
  if (actor === "You") {
    return translate(language, "workspaceUserLabel");
  }
  if (actor === "You (Voice)") {
    return translate(language, "workspaceUserVoiceLabel");
  }
  if (actor === "You (Video)") {
    return translate(language, "workspaceUserVideoLabel");
  }
  return actor;
};

const localizeInteractionMessage = (
  message: string,
  language: Language
): string => {
  const localizedDescriptor = parseLocalizedInteractionMessage(message);
  if (localizedDescriptor) {
    return translate(language, localizedDescriptor.key, localizedDescriptor.values);
  }

  if (message === "Opened new case workspace from the intake form.") {
    return translate(language, "mockCreatedCaseOpenMessage");
  }

  const storedDocumentMatch = message.match(STORED_DOCUMENT_MESSAGE_PATTERN);
  if (storedDocumentMatch?.groups?.count) {
    const count = Number(storedDocumentMatch.groups.count);
    return translate(
      language,
      count === 1
        ? "mockCreatedCaseStoredDocumentsSingular"
        : "mockCreatedCaseStoredDocumentsPlural",
      { count }
    );
  }

  const documentDeletedMatch = message.match(DOCUMENT_DELETED_MESSAGE_PATTERN);
  if (documentDeletedMatch?.groups?.deletedAt) {
    return translate(language, "sidebarDocumentDeletedHistory", {
      deletedAt: documentDeletedMatch.groups.deletedAt
    });
  }

  return message;
};

const formatFileSize = (size: number): string => {
  if (size >= 1024 * 1024) {
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }
  if (size >= 1024) {
    return `${Math.max(1, Math.round(size / 1024))} KB`;
  }
  return `${Math.max(1, size)} B`;
};

const buildDocumentRecord = (
  caseId: string,
  uploadedAt: string,
  document: CreateCaseDocumentInput,
  index: number
): CaseDocumentRecord => ({
  id: `${caseId}-document-${index + 1}`,
  caseId,
  kind: "uploaded",
  originalFilename: document.originalFilename,
  mimeType: document.mimeType,
  size: document.size,
  sizeLabel: formatFileSize(document.size),
  uploadedAt
});

const createMockCase = (input: CreateCaseInput, createdAt: string, id: string): CaseRecord => {
  const documents = input.documents.map((document, index) =>
    buildDocumentRecord(id, createdAt, document, index)
  );
  return {
    id,
    title: input.title.trim(),
    description: `${input.jurisdiction.trim()} matter involving ${input.opposingParty.trim()}.`,
    status: "In progress",
    createdAt,
    interactionHistory: [
      {
        id: `${id}-interaction-1`,
        createdAt,
        actor: "AI Lawyer",
        message: buildLocalizedInteractionMessage("mockCreatedCaseOpenMessage"),
        citations: []
      },
      {
        id: `${id}-interaction-2`,
        createdAt,
        actor: "System",
        message: buildLocalizedInteractionMessage(
          documents.length === 1
            ? "mockCreatedCaseStoredDocumentsSingular"
            : "mockCreatedCaseStoredDocumentsPlural",
          { count: documents.length }
        ),
        citations: []
      }
    ],
    selectedRole: "AI Lawyer",
    selectedMode: "Draft",
    selectedCommunicationMode: "Chat",
    workspace: {
      meta: `${input.jurisdiction.trim()} | ${documents.length} doc${documents.length === 1 ? "" : "s"}`,
      objective: `Prepare the case against ${input.opposingParty.trim()} and organize the uploaded evidence.`,
      nextAction: "Review the intake summary and start the AI lawyer chat when ready.",
      jurisdiction: input.jurisdiction.trim(),
      output: "Intake brief + document packet"
    },
    jurisdiction: input.jurisdiction.trim(),
    opposingParty: input.opposingParty.trim(),
    documents,
    citations: [],
    source: "mock"
  };
};

const localizeCaseRecord = (caseItem: CaseRecord, language: Language): CaseRecord => {
  const documentCount = caseItem.documents.length;

  const localizedWorkspace = isSeededCaseTemplateId(caseItem.id)
    ? (() => {
        const template = getMockCaseTemplate(language, caseItem.id);
        return {
          meta: template.meta,
          objective: template.objective,
          nextAction: template.nextAction,
          jurisdiction: caseItem.workspace.jurisdiction,
          output: template.output
        } satisfies CaseWorkspace;
      })()
    : {
        meta:
          caseItem.source === "mock"
            ? buildCreatedCaseMeta(caseItem.jurisdiction, documentCount, language)
            : caseItem.workspace.meta,
        objective:
          caseItem.source === "mock"
            ? translate(language, "mockCreatedCaseObjective", {
                opposingParty: caseItem.opposingParty
              })
            : caseItem.workspace.objective,
        nextAction:
          caseItem.source === "mock"
            ? translate(language, "mockCreatedCaseNextAction")
            : caseItem.workspace.nextAction,
        jurisdiction: caseItem.workspace.jurisdiction,
        output:
          caseItem.source === "mock"
            ? translate(language, "mockCreatedCaseOutput")
            : caseItem.workspace.output
      };

  return {
    ...caseItem,
    title: isSeededCaseTemplateId(caseItem.id)
      ? getMockCaseTemplate(language, caseItem.id).title
      : caseItem.title,
    description: isSeededCaseTemplateId(caseItem.id)
      ? getMockCaseTemplate(language, caseItem.id).description
      : caseItem.source === "mock"
        ? buildCreatedCaseDescription(caseItem.jurisdiction, caseItem.opposingParty, language)
        : caseItem.description,
    interactionHistory: caseItem.interactionHistory.map((interaction) => ({
      ...interaction,
      actor: localizeInteractionActor(interaction.actor, language),
      message: localizeInteractionMessage(interaction.message, language)
    })),
    workspace: localizedWorkspace
  };
};

const normalizeLegacyInteractionMessage = (message: string): string => {
  if (message === "Opened new case workspace from the intake form.") {
    return buildLocalizedInteractionMessage("mockCreatedCaseOpenMessage");
  }

  const storedDocumentMatch = message.match(STORED_DOCUMENT_MESSAGE_PATTERN);
  if (storedDocumentMatch?.groups?.count) {
    const count = Number(storedDocumentMatch.groups.count);
    return buildLocalizedInteractionMessage(
      count === 1
        ? "mockCreatedCaseStoredDocumentsSingular"
        : "mockCreatedCaseStoredDocumentsPlural",
      { count }
    );
  }

  const legacySystemMessagePrefixes: Array<{
    key: "workspaceApiUnavailablePrefix" | "workspaceApiRequestFailedPrefix";
    prefixes: string[];
  }> = [
    {
      key: "workspaceApiUnavailablePrefix",
      prefixes: [
        "Unable to reach API. ",
        "Nepodarilo sa spojiť s API. ",
        "API ist nicht erreichbar. "
      ]
    },
    {
      key: "workspaceApiRequestFailedPrefix",
      prefixes: [
        "API request failed. ",
        "Požiadavka na API zlyhala. ",
        "API-Anfrage ist fehlgeschlagen. "
      ]
    }
  ];

  for (const descriptor of legacySystemMessagePrefixes) {
    const prefix = descriptor.prefixes.find((item) => message.startsWith(item));
    if (prefix) {
      return buildLocalizedInteractionMessage(descriptor.key, {
        detail: message.slice(prefix.length)
      });
    }
  }

  return message;
};

const normalizeStoredDocument = (
  value: unknown,
  caseId: string
): CaseDocumentRecord | null => {
  if (!value || typeof value !== "object") {
    return null;
  }
  const candidate = value as Record<string, unknown>;
  if (
    typeof candidate.id !== "string" ||
    typeof candidate.originalFilename !== "string" ||
    typeof candidate.size !== "number" ||
    typeof candidate.uploadedAt !== "string"
  ) {
    return null;
  }
  return {
    id: candidate.id,
    caseId,
    kind: typeof candidate.kind === "string" && candidate.kind.trim() ? candidate.kind : "uploaded",
    originalFilename: candidate.originalFilename,
    mimeType: typeof candidate.mimeType === "string" ? candidate.mimeType : "application/octet-stream",
    size: candidate.size,
    sizeLabel:
      typeof candidate.sizeLabel === "string" && candidate.sizeLabel.trim()
        ? candidate.sizeLabel
        : formatFileSize(candidate.size),
    uploadedAt: candidate.uploadedAt
  };
};

const normalizeStoredCitation = (value: unknown): CaseCitation | null => {
  if (!value || typeof value !== "object") {
    return null;
  }
  const candidate = value as Record<string, unknown>;
  if (
    typeof candidate.id !== "string" ||
    typeof candidate.caseId !== "string" ||
    typeof candidate.sourceType !== "string" ||
    typeof candidate.title !== "string" ||
    typeof candidate.createdAt !== "string"
  ) {
    return null;
  }
  const sourceType =
    candidate.sourceType === "law" ||
    candidate.sourceType === "court_decision" ||
    candidate.sourceType === "case_document" ||
    candidate.sourceType === "web" ||
    candidate.sourceType === "other"
      ? candidate.sourceType
      : "other";
  const nullableString = (field: string): string | null =>
    typeof candidate[field] === "string" && candidate[field].trim()
      ? candidate[field]
      : null;
  return {
    id: candidate.id,
    caseId: candidate.caseId,
    questionMessageId: nullableString("questionMessageId"),
    answerMessageId: nullableString("answerMessageId"),
    sourceType,
    sourceId: nullableString("sourceId"),
    sourceUrl: nullableString("sourceUrl"),
    title: candidate.title,
    citationLabel: nullableString("citationLabel"),
    lawNumber: nullableString("lawNumber"),
    section: nullableString("section"),
    effectiveFrom: nullableString("effectiveFrom"),
    court: nullableString("court"),
    ecli: nullableString("ecli"),
    fileNumber: nullableString("fileNumber"),
    decisionDate: nullableString("decisionDate"),
    snippet: nullableString("snippet"),
    retrievalTool: nullableString("retrievalTool"),
    relevanceScore: typeof candidate.relevanceScore === "number" ? candidate.relevanceScore : null,
    createdAt: candidate.createdAt
  };
};

const normalizeStoredCase = (value: unknown): CaseRecord | null => {
  if (!value || typeof value !== "object") {
    return null;
  }
  const candidate = value as Record<string, unknown>;
  if (
    typeof candidate.id !== "string" ||
    typeof candidate.title !== "string" ||
    typeof candidate.description !== "string" ||
    typeof candidate.createdAt !== "string"
  ) {
    return null;
  }

  const rawDocuments = Array.isArray(candidate.documents) ? candidate.documents : [];
  const documents = rawDocuments
    .map((document) => normalizeStoredDocument(document, candidate.id as string))
    .filter((document): document is CaseDocumentRecord => document !== null);

  const rawWorkspace =
    candidate.workspace && typeof candidate.workspace === "object"
      ? (candidate.workspace as Record<string, unknown>)
      : {};
  const rawInteractions = Array.isArray(candidate.interactionHistory) ? candidate.interactionHistory : [];
  const citations = (Array.isArray(candidate.citations) ? candidate.citations : [])
    .map(normalizeStoredCitation)
    .filter((citation): citation is CaseCitation => citation !== null);
  const interactionHistory = rawInteractions
    .map((interaction) => {
      if (!interaction || typeof interaction !== "object") {
        return null;
      }
      const item = interaction as Record<string, unknown>;
      if (
        typeof item.id !== "string" ||
        typeof item.createdAt !== "string" ||
        typeof item.actor !== "string" ||
        typeof item.message !== "string"
      ) {
        return null;
      }
      return {
        id: item.id,
        createdAt: item.createdAt,
        actor: item.actor,
        message: normalizeLegacyInteractionMessage(item.message),
        citations: (Array.isArray(item.citations) ? item.citations : [])
          .map(normalizeStoredCitation)
          .filter((citation): citation is CaseCitation => citation !== null)
      } satisfies CaseInteraction;
    })
    .filter((interaction): interaction is CaseInteraction => interaction !== null);

  const status =
    candidate.status === "On hold" ||
    candidate.status === "Scheduled" ||
    candidate.status === "Completed"
      ? candidate.status
      : "In progress";
  const selectedRole = normalizeCaseRole(candidate.selectedRole);
  const selectedMode =
    candidate.selectedMode === "Review" ||
    candidate.selectedMode === "Live" ||
    candidate.selectedMode === "Archive"
      ? candidate.selectedMode
      : "Draft";
  const selectedCommunicationMode =
    candidate.selectedCommunicationMode === "Voice" ||
    candidate.selectedCommunicationMode === "Video"
      ? candidate.selectedCommunicationMode
      : "Chat";

  return {
    id: candidate.id,
    title: candidate.title,
    description: candidate.description,
    status,
    createdAt: candidate.createdAt,
    interactionHistory: normalizeInteractionHistory(interactionHistory),
    selectedRole,
    selectedMode,
    selectedCommunicationMode,
    workspace: {
      meta: typeof rawWorkspace.meta === "string" ? rawWorkspace.meta : "Mock workspace",
      objective:
        typeof rawWorkspace.objective === "string"
          ? rawWorkspace.objective
          : "Define scope, assign roles, and request initial documents.",
      nextAction:
        typeof rawWorkspace.nextAction === "string"
          ? rawWorkspace.nextAction
          : "Review the intake summary and start the AI lawyer chat.",
      jurisdiction:
        typeof rawWorkspace.jurisdiction === "string"
          ? rawWorkspace.jurisdiction
          : typeof candidate.jurisdiction === "string"
            ? candidate.jurisdiction
            : "TBD",
      output:
        typeof rawWorkspace.output === "string" ? rawWorkspace.output : "Intake brief"
    },
    jurisdiction: typeof candidate.jurisdiction === "string" ? candidate.jurisdiction : "TBD",
    opposingParty:
      typeof candidate.opposingParty === "string" ? candidate.opposingParty : "Unknown",
    documents,
    citations,
    source: "mock"
  };
};

const loadStoredCases = (): CaseRecord[] => {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const rawCases = window.localStorage.getItem(CASE_STORAGE_KEY);
    if (!rawCases) {
      return [];
    }
    const parsedCases: unknown = JSON.parse(rawCases);
    if (!Array.isArray(parsedCases)) {
      return [];
    }
    const normalized = parsedCases
      .map((item) => normalizeStoredCase(item))
      .filter((item): item is CaseRecord => item !== null)
      .filter((item) => !isSeededCaseTemplateId(item.id));
    return normalized;
  } catch {
    return [];
  }
};

const persistCases = (cases: CaseRecord[]): void => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(CASE_STORAGE_KEY, JSON.stringify(cases));
};

const toApiMessageContent = (
  content: string,
  communicationMode: CaseCommunicationMode
): string => {
  if (communicationMode === "Voice") {
    return `Voice message transcript from the user:\n${content}`;
  }
  if (communicationMode === "Video") {
    return `Video message transcript from the user:\n${content}`;
  }
  return content;
};

const mapApiStatus = (status: string): CaseStatus => {
  const normalized = status.trim().toLowerCase();
  if (["completed", "closed", "done"].includes(normalized)) {
    return "Completed";
  }
  if (["on_hold", "on hold", "paused"].includes(normalized)) {
    return "On hold";
  }
  if (["scheduled", "planned"].includes(normalized)) {
    return "Scheduled";
  }
  return "In progress";
};

const mapApiRole = (role: ApiCaseHistoryMessage["role"], agentName: string | null): string => {
  if (role === "user") {
    return "You";
  }
  if (role === "system") {
    return "System";
  }
  return assistantAgentDisplayName(agentName, "AI Lawyer");
};

const mapApiDocument = (caseId: string, document: ApiCaseDocument): CaseDocumentRecord => ({
  id: document.doc_id,
  caseId,
  kind: document.kind,
  originalFilename: document.original_filename,
  mimeType: "application/octet-stream",
  size: 0,
  sizeLabel: document.processing_status,
  uploadedAt: document.created_at
});

const mapApiCitation = (citation: ApiCaseCitation): CaseCitation => ({
  id: citation.id,
  caseId: citation.case_id,
  questionMessageId: citation.question_message_id,
  answerMessageId: citation.answer_message_id,
  sourceType: citation.source_type,
  sourceId: citation.source_id,
  sourceUrl: citation.source_url,
  title: citation.title,
  citationLabel: citation.citation_label,
  lawNumber: citation.law_number,
  section: citation.section,
  effectiveFrom: citation.effective_from,
  court: citation.court,
  ecli: citation.ecli,
  fileNumber: citation.file_number,
  decisionDate: citation.decision_date,
  snippet: citation.snippet,
  retrievalTool: citation.retrieval_tool,
  relevanceScore: citation.relevance_score,
  createdAt: citation.created_at
});

const buildDocumentViewerUrl = ({
  apiCase,
  document
}: {
  apiCase: ApiCase;
  document: CaseDocumentRecord;
}): string => {
  const params = new URLSearchParams({
    caseId: apiCase.case_id,
    docId: document.id,
    kind: document.kind,
    filename: document.originalFilename,
    caseTitle: apiCase.title,
    userId: apiCase.user_id
  });
  return `/app/documents/view?${params.toString()}`;
};

const appendGeneratedDocumentLinksToHistory = ({
  apiCase,
  messages,
  documents
}: {
  apiCase: ApiCase;
  messages: ApiCaseHistoryMessage[];
  documents: CaseDocumentRecord[];
}): ApiCaseHistoryMessage[] => {
  const generatedDocuments = documents.filter(isUserVisibleGeneratedDocument);
  if (generatedDocuments.length === 0) {
    return messages;
  }
  let lastAssistantIndex = -1;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index]?.role === "assistant") {
      lastAssistantIndex = index;
      break;
    }
  }
  if (lastAssistantIndex < 0) {
    return messages;
  }
  const lastAssistant = messages[lastAssistantIndex];
  if (!lastAssistant) {
    return messages;
  }
  if (lastAssistant.content.includes("/app/documents/view?")) {
    return messages;
  }
  const heading = generatedDocuments.length === 1 ? "Generated document:" : "Generated documents:";
  const links = generatedDocuments.map((document) => {
    const url = buildDocumentViewerUrl({ apiCase, document });
    return `- [${document.originalFilename}](${url})`;
  });
  const appended: ApiCaseHistoryMessage = {
    ...lastAssistant,
    content: `${lastAssistant.content.trim()}\n\n${heading}\n${links.join("\n")}`.trim()
  };
  return messages.map((message, index) => (index === lastAssistantIndex ? appended : message));
};

const mapApiCase = (
  apiCase: ApiCase,
  historyMessages: ApiCaseHistoryMessage[] = [],
  historyDocuments: ApiCaseDocument[] = [],
  historyCitations: ApiCaseCitation[] = []
): CaseRecord => {
  const documents = historyDocuments.map((document) => mapApiDocument(apiCase.case_id, document));
  const legalDocumentCount = documents.filter(isUserVisibleGeneratedDocument).length;
  const messagesWithDocumentLinks = appendGeneratedDocumentLinksToHistory({
    apiCase,
    messages: historyMessages,
    documents
  });
  const createdAt = apiCase.created_at;
  const caseCitations = historyCitations.map(mapApiCitation);
  return {
    id: apiCase.case_id,
    title: apiCase.title,
    description: apiCase.company_id
      ? `Company case ${apiCase.company_id}`
      : `Case ${apiCase.case_id}`,
    status: mapApiStatus(apiCase.status),
    createdAt,
    interactionHistory: messagesWithDocumentLinks.map((message) => ({
      id: message.communication_id,
      createdAt: message.created_at,
      actor: mapApiRole(message.role, message.agent_name),
      message: message.role === "assistant"
        ? normalizeAssistantPresentationText(message.content)
        : message.content,
      citations: (message.citations ?? []).map(mapApiCitation)
    })),
    selectedRole: "AI Lawyer",
    selectedMode: "Draft",
    selectedCommunicationMode: "Chat",
    workspace: {
      meta: `${legalDocumentCount} legal document${legalDocumentCount === 1 ? "" : "s"} / ${historyMessages.length} message${historyMessages.length === 1 ? "" : "s"}`,
      objective: apiCase.title,
      nextAction: "Open the selected case data and continue the chat.",
      jurisdiction: "SK",
      output: "Case history + documents"
    },
    jurisdiction: "SK",
    opposingParty: "",
    documents,
    citations: caseCitations,
    source: "api"
  };
};

const loadApiCaseWithHistory = async (userId: string, apiCase: ApiCase): Promise<CaseRecord> => {
  try {
    const history = await getCaseHistory(userId, apiCase.case_id, 200);
    return mapApiCase(apiCase, history.messages, history.documents, history.citations ?? []);
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Unable to load case history.";
    consoleLogger.warn("Unable to load API case history; showing case without counts", {
      caseId: apiCase.case_id,
      detail
    });
    return mapApiCase(apiCase);
  }
};

export const CaseProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { language } = useLanguage();
  const { isAuthenticated, user } = useAuth();
  const [storedCases, setStoredCases] = React.useState<CaseRecord[]>(() => loadStoredCases());
  const [activeCaseId, setActiveCaseId] = React.useState<string | null>(null);
  const [hasSelectedCase, setHasSelectedCase] = React.useState(false);
  const [continueRequested, setContinueRequested] = React.useState(false);
  const [isLoadingCases, setIsLoadingCases] = React.useState(false);
  const [caseLoadError, setCaseLoadError] = React.useState<string | null>(null);
  const sessionIdsByCaseRef = React.useRef<Record<string, CaseSessionCacheRecord>>({});

  React.useEffect(() => {
    persistCases(storedCases.filter((caseItem) => caseItem.source === "mock"));
  }, [storedCases]);

  React.useEffect(() => {
    let isCancelled = false;

    const loadApiCases = async () => {
      if (!isAuthenticated || !user?.userId) {
        setStoredCases(loadStoredCases());
        setActiveCaseId(null);
        setHasSelectedCase(false);
        return;
      }

      setIsLoadingCases(true);
      setCaseLoadError(null);
      try {
        const apiCases = await listCases(user.userId);
        if (isCancelled) {
          return;
        }
        setStoredCases(apiCases.map((item) => mapApiCase(item)));
        setIsLoadingCases(false);

        void Promise.all(
          apiCases.map(async (item) => {
            const hydratedCase = await loadApiCaseWithHistory(user.userId, item);
            if (isCancelled) {
              return;
            }
            setStoredCases((previous) =>
              previous.map((caseItem) =>
                caseItem.id === hydratedCase.id
                  ? {
                      ...hydratedCase,
                      selectedRole: caseItem.selectedRole,
                      selectedMode: caseItem.selectedMode,
                      selectedCommunicationMode: caseItem.selectedCommunicationMode
                    }
                  : caseItem
              )
            );
          })
        );
      } catch (error) {
        if (isCancelled) {
          return;
        }
        const detail = error instanceof Error ? error.message : "Unable to load cases.";
        setCaseLoadError(detail);
        consoleLogger.warn("Unable to load API cases; using local fallback cases", { detail });
        setStoredCases(loadStoredCases());
      } finally {
        if (!isCancelled) {
          setIsLoadingCases(false);
        }
      }
    };

    void loadApiCases();

    return () => {
      isCancelled = true;
    };
  }, [isAuthenticated, user?.userId]);

  React.useEffect(() => {
    if (activeCaseId && !storedCases.some((caseItem) => caseItem.id === activeCaseId)) {
      setActiveCaseId(null);
      setHasSelectedCase(false);
    }
  }, [activeCaseId, storedCases]);

  const cases = React.useMemo(() => {
    return storedCases.map((caseItem) => localizeCaseRecord(caseItem, language));
  }, [language, storedCases]);

  const documents = React.useMemo(() => {
    return cases
      .flatMap((caseItem) =>
        caseItem.documents
          .filter(isUserVisibleGeneratedDocument)
          .map((document) => ({
            ...document,
            caseTitle: caseItem.title
          }))
      )
      .sort((left, right) => right.uploadedAt.localeCompare(left.uploadedAt));
  }, [cases]);

  const activeCase = React.useMemo(() => {
    if (!activeCaseId) {
      return null;
    }
    return cases.find((caseItem) => caseItem.id === activeCaseId) ?? null;
  }, [activeCaseId, cases]);

  const loadCaseData = React.useCallback(
    async (caseId: string) => {
      if (!user?.userId) {
        return null;
      }
      try {
        const apiCase = storedCases.find((caseItem) => caseItem.id === caseId);
        const history = await getCaseHistory(user.userId, caseId, 200);
        const refreshedCase = apiCase
          ? mapApiCase(
              {
                case_id: apiCase.id,
                user_id: user.userId,
                company_id: null,
                title: apiCase.title,
                status: apiCase.status,
                created_at: apiCase.createdAt,
                updated_at: apiCase.createdAt
              },
              history.messages,
              history.documents,
              history.citations ?? []
            )
          : null;
        setStoredCases((prev) =>
          prev.map((caseItem) =>
            caseItem.id === caseId && refreshedCase ? refreshedCase : caseItem
          )
        );
        if (!apiCase) {
          consoleLogger.info("Loaded selected case data", { caseId });
        }
        return refreshedCase;
      } catch (error) {
        const detail = error instanceof Error ? error.message : "Unable to load selected case.";
        setCaseLoadError(detail);
        consoleLogger.warn("Unable to load selected case data", { caseId, detail });
        return null;
      }
    },
    [storedCases, user?.userId]
  );

  const createCase = React.useCallback(async (input: CreateCaseInput) => {
    const createdAt = new Date().toISOString();
    let newCase: CaseRecord;
    if (user?.userId) {
      try {
        const apiCase = await createApiCase({ userId: user.userId, title: input.title.trim() });
        let history: Awaited<ReturnType<typeof getCaseHistory>> = {
          messages: [],
          documents: [],
          has_more: false
        };
        const files = input.documents.map((document) => document.file).filter((file): file is File => Boolean(file));
        if (files.length > 0) {
          history = await uploadApiCaseDocuments({
            userId: user.userId,
            caseId: apiCase.case_id,
            files
          });
        }
        newCase = mapApiCase(apiCase, history.messages, history.documents, history.citations ?? []);
      } catch (error) {
        const detail = error instanceof Error ? error.message : "Unable to create API case.";
        setCaseLoadError(detail);
        consoleLogger.warn("Unable to create API case; using local fallback case", { detail });
        newCase = createMockCase(input, createdAt, `case-${Date.now()}`);
      }
    } else {
      newCase = createMockCase(input, createdAt, `case-${Date.now()}`);
    }
    setStoredCases((prev) => [newCase, ...prev]);
    setActiveCaseId(newCase.id);
    setHasSelectedCase(true);
    setContinueRequested(false);
    consoleLogger.info("Created mock case in frontend state", {
      caseId: newCase.id,
      documentCount: newCase.documents.length
    });
    return localizeCaseRecord(newCase, language);
  }, [language, user?.userId]);

  const deleteCase = React.useCallback(
    async (caseId: string) => {
      const target = storedCases.find((caseItem) => caseItem.id === caseId);
      if (!target) {
        throw new Error(`Case ${caseId} was not found.`);
      }
      if (target.source === "api") {
        if (!user?.userId) {
          throw new Error("Sign in before deleting a case.");
        }
        await deleteApiCase(user.userId, caseId);
      }
      delete sessionIdsByCaseRef.current[caseId];
      setStoredCases((previous) => {
        const remaining = previous.filter((caseItem) => caseItem.id !== caseId);
        setActiveCaseId((current) => {
          if (current !== caseId) {
            return current;
          }
          const nextCaseId = remaining[0]?.id ?? null;
          setHasSelectedCase(Boolean(nextCaseId));
          return nextCaseId;
        });
        return remaining;
      });
    },
    [storedCases, user?.userId]
  );

  const deleteDocument = React.useCallback(
    async (caseId: string, docId: string) => {
      const target = storedCases.find((caseItem) => caseItem.id === caseId);
      if (!target?.documents.some((document) => document.id === docId)) {
        throw new Error(`Document ${docId} was not found.`);
      }
      if (target.source === "api") {
        if (!user?.userId) {
          throw new Error("Sign in before deleting a document.");
        }
        const event = await deleteApiCaseDocument(user.userId, caseId, docId);
        setStoredCases((previous) =>
          previous.map((caseItem) =>
            caseItem.id === caseId
              ? {
                  ...caseItem,
                  documents: caseItem.documents.filter((document) => document.id !== docId),
                  interactionHistory: [
                    ...caseItem.interactionHistory,
                    {
                      id: event.communication_id,
                      createdAt: event.deleted_at,
                      actor: "System",
                      message: `Document deleted at ${event.deleted_at}.`,
                      citations: []
                    }
                  ]
                }
              : caseItem
          )
        );
        return;
      }
      const deletedAt = new Date().toISOString();
      setStoredCases((previous) =>
        previous.map((caseItem) =>
          caseItem.id === caseId
            ? {
                ...caseItem,
                documents: caseItem.documents.filter((document) => document.id !== docId),
                interactionHistory: [
                  ...caseItem.interactionHistory,
                  {
                    id: `${caseId}-document-deleted-${Date.now()}`,
                    createdAt: deletedAt,
                    actor: "System",
                    message: `Document deleted at ${deletedAt}.`,
                    citations: []
                  }
                ]
              }
            : caseItem
        )
      );
    },
    [storedCases, user?.userId]
  );

  const setActiveCase = React.useCallback((caseId: string) => {
    setActiveCaseId(caseId);
  }, []);

  const selectCase = React.useCallback((caseId: string) => {
    setActiveCaseId(caseId);
    setHasSelectedCase(true);
    setContinueRequested(false);
    const selected = storedCases.find((caseItem) => caseItem.id === caseId);
    if (selected?.source === "api") {
      void loadCaseData(caseId);
    }
  }, [loadCaseData, storedCases]);

  const updateCase = React.useCallback((caseId: string, update: Partial<CaseRecord>) => {
    const normalizedUpdate =
      update.selectedRole === undefined ? update : { ...update, selectedRole: normalizeCaseRole(update.selectedRole) };
    setStoredCases((prev) =>
      prev.map((caseItem) => (caseItem.id === caseId ? { ...caseItem, ...normalizedUpdate } : caseItem))
    );
  }, []);

  const addInteraction = React.useCallback(
    (caseId: string, actor: string, message: string) => {
      const createdAt = new Date().toISOString();
      const interaction: CaseInteraction = {
        id: `${caseId}-${Date.now()}`,
        createdAt,
        actor,
        message,
        citations: []
      };
      setStoredCases((prev) =>
        prev.map((caseItem) =>
          caseItem.id === caseId
            ? {
                ...caseItem,
                interactionHistory: [
                  ...(isUserInteractionActor(actor)
                    ? stripSeededAssistantIntro(caseItem.interactionHistory)
                    : caseItem.interactionHistory),
                  interaction
                ]
              }
            : caseItem
        )
      );
    },
    []
  );

  const ensureCaseSessionId = React.useCallback(async (caseId: string): Promise<string> => {
    const existingSession = sessionIdsByCaseRef.current[caseId];
    if (existingSession && existingSession.language === language) {
      return existingSession.sessionId;
    }

      const session = await createChatSession({ language, userId: user?.userId, caseId });
    sessionIdsByCaseRef.current[caseId] = {
      language,
      sessionId: session.id
    };

    consoleLogger.info("Created API session for case", {
      caseId,
      sessionId: session.id
    });

    return session.id;
  }, [language, user?.userId]);

  const sendCaseMessage = React.useCallback(
    async (input: SendCaseMessageInput): Promise<SendCaseMessageResult> => {
      const caseExists = storedCases.some((caseItem) => caseItem.id === input.caseId);
      if (!caseExists) {
        throw new Error(`Case ${input.caseId} was not found.`);
      }
      const normalizedContent = input.content.trim();
      if (!normalizedContent) {
        throw new Error("Message content is required.");
      }

      const sessionId = await ensureCaseSessionId(input.caseId);
      const apiContent = toApiMessageContent(normalizedContent, input.communicationMode);
      consoleLogger.info("Sending case communication through API", {
        caseId: input.caseId,
        sessionId,
        communicationMode: input.communicationMode
      });

      const assistantMessage = await replyToSession({
        sessionId,
        content: apiContent
      });

      return {
        sessionId,
        assistantActor: assistantAgentDisplayName(assistantMessage.agent_name, "AI Assistant"),
        assistantMessage: normalizeAssistantPresentationText(assistantMessage.content)
      };
    },
    [storedCases, ensureCaseSessionId]
  );

  const setCaseRole = React.useCallback(
    (caseId: string, role: CaseRole) => {
      updateCase(caseId, { selectedRole: normalizeCaseRole(role) });
    },
    [updateCase]
  );

  const setCaseMode = React.useCallback(
    (caseId: string, mode: CaseMode) => {
      updateCase(caseId, { selectedMode: mode });
    },
    [updateCase]
  );

  const setCaseCommunicationMode = React.useCallback(
    (caseId: string, mode: CaseCommunicationMode) => {
      updateCase(caseId, { selectedCommunicationMode: mode });
    },
    [updateCase]
  );

  const value = React.useMemo(
    () => ({
      cases,
      documents,
      activeCaseId,
      activeCase,
      hasSelectedCase,
      continueRequested,
      isLoadingCases,
      caseLoadError,
      createCase,
      deleteCase,
      deleteDocument,
      loadCaseData,
      setActiveCase,
      selectCase,
      setContinueRequested,
      addInteraction,
      sendCaseMessage,
      updateCase,
      setCaseRole,
      setCaseMode,
      setCaseCommunicationMode
    }),
    [
      cases,
      documents,
      activeCaseId,
      activeCase,
      hasSelectedCase,
      continueRequested,
      isLoadingCases,
      caseLoadError,
      createCase,
      deleteCase,
      deleteDocument,
      loadCaseData,
      setActiveCase,
      selectCase,
      setContinueRequested,
      addInteraction,
      sendCaseMessage,
      updateCase,
      setCaseRole,
      setCaseMode,
      setCaseCommunicationMode
    ]
  );

  return <CaseContext.Provider value={value}>{children}</CaseContext.Provider>;
};

export const useCases = () => {
  const context = React.useContext(CaseContext);
  if (!context) {
    throw new Error("useCases must be used within a CaseProvider.");
  }
  return context;
};
