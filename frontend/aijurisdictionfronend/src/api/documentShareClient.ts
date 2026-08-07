import { chatApiRuntimeConfig, ApiRequestError, parseApiErrorResponse } from "./chatClient";

const request = async <T>(path: string, init: RequestInit): Promise<T> => {
  const response = await fetch(`${chatApiRuntimeConfig().baseUrl}${path}`, init);
  if (!response.ok) {
    const detail = await parseApiErrorResponse(response);
    throw new ApiRequestError("http", detail.message, response.status);
  }
  return response.json() as Promise<T>;
};

export const requestDocumentShareCode = (shareToken: string) =>
  request<{ message: string; locale: "en" | "sk" | "de" }>(
    `/v1/document-shares/${encodeURIComponent(shareToken)}/request-code`,
    { method: "POST" }
  );

export const verifyDocumentShareCode = (shareToken: string, code: string) =>
  request<{ session_token: string; expires_at: string; locale: "en" | "sk" | "de" }>(
    `/v1/document-shares/${encodeURIComponent(shareToken)}/verify`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code }) }
  );

export const fetchSharedDocumentPdf = async (sessionToken: string): Promise<Blob> => {
  const response = await fetch(`${chatApiRuntimeConfig().baseUrl}/v1/document-shares/content/pdf`, {
    headers: { Authorization: `Bearer ${sessionToken}` },
    cache: "no-store",
    referrerPolicy: "no-referrer"
  });
  if (!response.ok) {
    const detail = await parseApiErrorResponse(response);
    throw new ApiRequestError("http", detail.message, response.status);
  }
  return response.blob();
};
