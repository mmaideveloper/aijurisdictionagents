import { createChatSession, replyToSession } from "./api/chatClient";

export type CaseMode = "new" | "existing";

export type AssistantRequest = {
  question: string;
  caseMode: CaseMode;
  caseId: string;
  country: string;
  language: string;
  consentGateway: boolean;
  consentDocuments: boolean;
  consentThirdParty: boolean;
  files: File[];
};

export type AssistantResponse = {
  caseId: string;
  answer: string;
  status: "completed" | "needs_input" | "queued";
  usedFallback: boolean;
  citations: string[];
  storedDocuments: string[];
  nextActions: string[];
};

type GatewayPayload = {
  case_id?: string;
  caseId?: string;
  answer?: string;
  response?: string;
  status?: AssistantResponse["status"];
  citations?: Array<string | { label?: string; source?: string; title?: string }>;
  stored_documents?: Array<string | { filename?: string; name?: string }>;
  storedDocuments?: Array<string | { filename?: string; name?: string }>;
  next_actions?: string[];
  nextActions?: string[];
};

type NormalizableValue =
  | string
  | {
      label?: string;
      source?: string;
      title?: string;
      filename?: string;
      name?: string;
    };

const DEFAULT_GATEWAY_PATH = "/api/assistant/cases/answer";

export async function submitAssistantQuestion(
  request: AssistantRequest
): Promise<AssistantResponse> {
  const endpoint = getGatewayEndpoint();
  const form = new FormData();

  form.set("question", request.question);
  form.set("case_mode", request.caseMode);
  form.set("case_id", request.caseId);
  form.set("country", request.country);
  form.set("language", request.language);
  form.set(
    "consents",
    JSON.stringify({
      assistant_gateway: request.consentGateway,
      document_processing: request.consentDocuments,
      third_party_tools: request.consentThirdParty
    })
  );

  request.files.forEach((file) => form.append("documents", file, file.name));

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      body: form,
      headers: {
        Accept: "application/json"
      }
    });

    if (!response.ok) {
      throw new Error(`Assistant Gateway returned ${response.status}`);
    }

    const payload = (await response.json()) as GatewayPayload;
    return normalizeGatewayPayload(payload, request);
  } catch (error) {
    return submitQuestionThroughChatApi(request, error);
  }
}

function getGatewayEndpoint(): string {
  const configuredEndpoint = import.meta.env.VITE_ASSISTANT_GATEWAY_URL as string | undefined;
  return configuredEndpoint?.trim() || DEFAULT_GATEWAY_PATH;
}

function normalizeGatewayPayload(
  payload: GatewayPayload,
  request: AssistantRequest
): AssistantResponse {
  const documents = payload.stored_documents ?? payload.storedDocuments ?? [];
  const caseId = (payload.case_id ?? payload.caseId ?? request.caseId) || createDraftCaseId();

  return {
    caseId,
    answer:
      payload.answer ??
      payload.response ??
      "Assistant Gateway accepted the request but did not return an answer body.",
    status: payload.status ?? "completed",
    usedFallback: false,
    citations: normalizeStringList(payload.citations),
    storedDocuments: normalizeStringList(documents),
    nextActions: payload.next_actions ?? payload.nextActions ?? []
  };
}

function normalizeStringList(values: NormalizableValue[] | undefined): string[] {
  if (!values) {
    return [];
  }

  return values
    .map((value) => {
      if (typeof value === "string") {
        return value;
      }

      return value.label ?? value.source ?? value.title ?? value.filename ?? value.name ?? "";
    })
    .filter(Boolean);
}

async function submitQuestionThroughChatApi(
  request: AssistantRequest,
  gatewayError: unknown
): Promise<AssistantResponse> {
  try {
    const session = await createChatSession({
      caseId: request.caseMode === "existing" ? request.caseId : undefined,
      country: request.country,
      language: request.language
    });
    const reply = await replyToSession({
      sessionId: session.id,
      content: buildChatApiQuestion(request, gatewayError)
    });
    const caseId = request.caseMode === "existing" && request.caseId ? request.caseId : session.case_id || createDraftCaseId();
    const fileNames = request.files.map((file) => file.name);

    return {
      caseId,
      status: "completed",
      usedFallback: false,
      citations: [],
      storedDocuments: fileNames,
      nextActions: fileNames.length
        ? ["Upload handling through Assistant Gateway was unavailable; answer was generated from the typed question only."]
        : [],
      answer: reply.content
    };
  } catch (chatError) {
    return buildGatewayUnavailableResponse(request, gatewayError, chatError);
  }
}

function buildChatApiQuestion(request: AssistantRequest, gatewayError: unknown): string {
  const fileNames = request.files.map((file) => file.name);
  const gatewayErrorText = gatewayError instanceof Error ? gatewayError.message : "Gateway request failed";
  const lines = [request.question.trim()];

  if (fileNames.length > 0) {
    lines.push(`Attached document filenames: ${fileNames.join(", ")}.`);
    lines.push("Document upload through Assistant Gateway was unavailable, so answer from the typed facts only.");
  }
  lines.push(`Assistant Gateway unavailable: ${gatewayErrorText}. Use the JurisDigta chat API to answer the legal question directly.`);

  return lines.join("\n\n");
}

function buildGatewayUnavailableResponse(
  request: AssistantRequest,
  gatewayError: unknown,
  chatError: unknown
): AssistantResponse {
  const caseId = request.caseMode === "existing" && request.caseId ? request.caseId : createDraftCaseId();
  const fileNames = request.files.map((file) => file.name);
  const gatewayErrorText = gatewayError instanceof Error ? gatewayError.message : "Gateway request failed";
  const chatErrorText = chatError instanceof Error ? chatError.message : "Chat API request failed";

  return {
    caseId,
    status: "needs_input",
    usedFallback: false,
    citations: fileNames,
    storedDocuments: fileNames,
    nextActions: ["Retry after the JurisDigta API is reachable."],
    answer: [
      "JurisDigta assistant could not produce an answer because both backends were unavailable.",
      `Assistant Gateway error: ${gatewayErrorText}.`,
      `Chat API error: ${chatErrorText}.`
    ].join("\n\n")
  };
}

function createDraftCaseId(): string {
  if ("randomUUID" in crypto) {
    return `CASE-${crypto.randomUUID()}`;
  }

  return `CASE-${Date.now().toString(36).toUpperCase()}`;
}
