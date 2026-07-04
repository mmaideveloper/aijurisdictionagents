import { chatApiRuntimeConfig, ApiRequestError, parseApiErrorResponse } from "./chatClient";
import { consoleLogger } from "../logging/consoleLogger";

export type ApiCase = {
  case_id: string;
  user_id: string;
  company_id: string | null;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type ApiCaseHistoryMessage = {
  communication_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  agent_name: string | null;
  created_at: string;
};

export type ApiCaseDocument = {
  doc_id: string;
  kind: string;
  version: number;
  original_filename: string;
  processing_status: string;
  processing_error: string | null;
  processed_at: string | null;
  created_at: string;
};

export type ApiCaseHistory = {
  messages: ApiCaseHistoryMessage[];
  has_more: boolean;
  documents: ApiCaseDocument[];
};

export type CreateApiCaseInput = {
  userId: string;
  title: string;
};

export type UploadApiCaseDocumentsInput = {
  userId: string;
  caseId: string;
  files: File[];
};

export type SendCaseDocumentEmailInput = {
  userId: string;
  caseId: string;
  docIds: string[];
  recipient: string;
  caseSubject?: string;
};

export type FetchCaseDocumentInput = {
  userId: string;
  caseId: string;
  docId: string;
  disposition?: "attachment" | "inline";
  format?: "source" | "pdf";
  signal?: AbortSignal;
};

export type FetchedCaseDocument = {
  blob: Blob;
  contentType: string;
  filename: string;
};

export type SendCaseDocumentEmailResult = {
  email_id: string;
  recipient: string;
  case_subject: string;
  attachment_count: number;
  correlation_id: string;
};

const requestJson = async <T>(path: string, init: RequestInit): Promise<T> => {
  const config = chatApiRuntimeConfig();
  const method = init.method || "GET";
  const url = `${config.baseUrl}${path}`;

  consoleLogger.info("Sending case API request", { method, path, url });

  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (error) {
    consoleLogger.error("Case API network request failed", { method, path, url }, error);
    throw new ApiRequestError(
      "network",
      "Network request failed. Check API availability, CORS, and URL/protocol."
    );
  }

  if (!response.ok) {
    const detail = await parseApiErrorResponse(response);
    consoleLogger.warn("Case API request failed", {
      method,
      path,
      status: response.status,
      detail: detail.message,
      code: detail.code
    });
    throw new ApiRequestError("http", detail.message, response.status, {
      code: detail.code,
      params: detail.params
    });
  }

  return (await response.json()) as T;
};

export const listCases = async (userId: string): Promise<ApiCase[]> => {
  const config = chatApiRuntimeConfig();
  return requestJson<ApiCase[]>(`/v1/cases?user_id=${encodeURIComponent(userId)}`, {
    method: "GET",
    headers: {
      "x-api-key": config.apiKey
    }
  });
};

export const createApiCase = async (input: CreateApiCaseInput): Promise<ApiCase> => {
  const config = chatApiRuntimeConfig();
  return requestJson<ApiCase>("/v1/cases", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": config.apiKey
    },
    body: JSON.stringify({
      user_id: input.userId,
      title: input.title
    })
  });
};

export const getCaseHistory = async (
  userId: string,
  caseId: string,
  limit = 20
): Promise<ApiCaseHistory> => {
  const config = chatApiRuntimeConfig();
  const params = new URLSearchParams({
    user_id: userId,
    limit: String(limit)
  });
  return requestJson<ApiCaseHistory>(`/v1/cases/${caseId}/history?${params.toString()}`, {
    method: "GET",
    headers: {
      "x-api-key": config.apiKey
    }
  });
};

export const uploadApiCaseDocuments = async (
  input: UploadApiCaseDocumentsInput
): Promise<ApiCaseHistory> => {
  const config = chatApiRuntimeConfig();
  const form = new FormData();
  input.files.forEach((file) => form.append("files", file));

  await requestJson<unknown>(
    `/v1/cases/${input.caseId}/documents?user_id=${encodeURIComponent(input.userId)}`,
    {
      method: "POST",
      headers: {
        "x-api-key": config.apiKey
      },
      body: form
    }
  );

  return getCaseHistory(input.userId, input.caseId);
};

export const buildCaseDocumentUrl = ({
  userId,
  caseId,
  docId,
  disposition = "attachment",
  format = "source"
}: {
  userId: string;
  caseId: string;
  docId: string;
  disposition?: "attachment" | "inline";
  format?: "source" | "pdf";
}): string => {
  const config = chatApiRuntimeConfig();
  const params = new URLSearchParams({
    user_id: userId,
    disposition
  });
  const documentPath = `/v1/cases/${encodeURIComponent(caseId)}/documents/${encodeURIComponent(docId)}${
    format === "pdf" ? "/pdf" : ""
  }`;
  return `${config.baseUrl}${documentPath}?${params.toString()}`;
};

const extractFilenameFromContentDisposition = (header: string | null): string | null => {
  if (!header) {
    return null;
  }
  const encodedMatch = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (encodedMatch?.[1]) {
    try {
      return decodeURIComponent(encodedMatch[1].trim().replace(/^"|"$/g, ""));
    } catch {
      return encodedMatch[1].trim().replace(/^"|"$/g, "");
    }
  }
  const plainMatch = header.match(/filename="?([^";]+)"?/i);
  return plainMatch?.[1]?.trim() || null;
};

export const fetchCaseDocumentBlob = async ({
  userId,
  caseId,
  docId,
  disposition = "attachment",
  format = "source",
  signal
}: FetchCaseDocumentInput): Promise<FetchedCaseDocument> => {
  const config = chatApiRuntimeConfig();
  const url = buildCaseDocumentUrl({ userId, caseId, docId, disposition, format });

  consoleLogger.info("Fetching case document", {
    path: `/v1/cases/${caseId}/documents/${docId}${format === "pdf" ? "/pdf" : ""}`,
    disposition,
    format,
    url
  });

  let response: Response;
  try {
    response = await fetch(url, {
      method: "GET",
      headers: {
        "x-api-key": config.apiKey
      },
      signal
    });
  } catch (error) {
    consoleLogger.error("Case document request failed", { url, disposition, format }, error);
    throw new ApiRequestError(
      "network",
      "Network request failed. Check API availability, CORS, and URL/protocol."
    );
  }

  if (!response.ok) {
    const detail = await parseApiErrorResponse(response);
    consoleLogger.warn("Case document request failed", {
      status: response.status,
      detail: detail.message,
      code: detail.code,
      disposition,
      format
    });
    throw new ApiRequestError("http", detail.message, response.status, {
      code: detail.code,
      params: detail.params
    });
  }

  const contentType = response.headers.get("Content-Type") || "application/octet-stream";
  const filename =
    extractFilenameFromContentDisposition(response.headers.get("Content-Disposition")) ||
    `document-${docId}${format === "pdf" ? ".pdf" : ""}`;

  return {
    blob: await response.blob(),
    contentType,
    filename
  };
};

export const fetchCaseExportBlob = async ({
  userId,
  caseId,
  signal
}: {
  userId: string;
  caseId: string;
  signal?: AbortSignal;
}): Promise<FetchedCaseDocument> => {
  const config = chatApiRuntimeConfig();
  const params = new URLSearchParams({ user_id: userId });
  const path = `/v1/cases/${encodeURIComponent(caseId)}/export?${params.toString()}`;
  const url = `${config.baseUrl}${path}`;

  consoleLogger.info("Fetching case export", { path, url });

  let response: Response;
  try {
    response = await fetch(url, {
      method: "GET",
      headers: {
        "x-api-key": config.apiKey
      },
      signal
    });
  } catch (error) {
    consoleLogger.error("Case export request failed", { url }, error);
    throw new ApiRequestError(
      "network",
      "Network request failed. Check API availability, CORS, and URL/protocol."
    );
  }

  if (!response.ok) {
    const detail = await parseApiErrorResponse(response);
    consoleLogger.warn("Case export request failed", {
      status: response.status,
      detail: detail.message,
      code: detail.code
    });
    throw new ApiRequestError("http", detail.message, response.status, {
      code: detail.code,
      params: detail.params
    });
  }

  return {
    blob: await response.blob(),
    contentType: response.headers.get("Content-Type") || "application/zip",
    filename: extractFilenameFromContentDisposition(response.headers.get("Content-Disposition")) || `${caseId}-export.zip`
  };
};

export const sendCaseDocumentEmail = async (
  input: SendCaseDocumentEmailInput
): Promise<SendCaseDocumentEmailResult> => {
  const config = chatApiRuntimeConfig();
  return requestJson<SendCaseDocumentEmailResult>(
    `/v1/cases/${encodeURIComponent(input.caseId)}/documents/send-email`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": config.apiKey
      },
      body: JSON.stringify({
        user_id: input.userId,
        recipient: input.recipient,
        case_subject: input.caseSubject || "",
        doc_ids: input.docIds
      })
    }
  );
};
