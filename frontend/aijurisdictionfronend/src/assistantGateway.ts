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
    return buildLocalFallback(request, error);
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

function buildLocalFallback(request: AssistantRequest, error: unknown): AssistantResponse {
  const caseId = request.caseMode === "existing" && request.caseId ? request.caseId : createDraftCaseId();
  const fileNames = request.files.map((file) => file.name);
  const gatewayError = error instanceof Error ? error.message : "Gateway request failed";

  return {
    caseId,
    status: "needs_input",
    usedFallback: true,
    citations: fileNames,
    storedDocuments: fileNames,
    nextActions: [
      "Confirm identity and consent before production execution.",
      "Persist the question, uploaded files, and answer in the selected case.",
      "Route legal research through MCP tools only after Assistant Gateway policy checks."
    ],
    answer: [
      `Local demo answer for case ${caseId}.`,
      `Question received: ${request.question}`,
      fileNames.length
        ? `Documents prepared for upload: ${fileNames.join(", ")}.`
        : "No documents were attached to this request.",
      `Gateway note: ${gatewayError}.`
    ].join("\n\n")
  };
}

function createDraftCaseId(): string {
  if ("randomUUID" in crypto) {
    return `CASE-${crypto.randomUUID()}`;
  }

  return `CASE-${Date.now().toString(36).toUpperCase()}`;
}
