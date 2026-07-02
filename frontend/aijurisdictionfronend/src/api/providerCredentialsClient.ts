import { ApiRequestError, chatApiRuntimeConfig } from "./chatClient";
import { consoleLogger } from "../logging/consoleLogger";

export type ProviderCredential = {
  credential_id: string;
  provider_key: string;
  display_name: string;
  description: string;
  endpoint: string;
  deployment: string;
  embeddings_model: string;
  api_version: string;
  auth_method: string;
  secret_name: string;
  has_secret: boolean;
  metadata: Record<string, unknown>;
  is_enabled: boolean;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
};

export type ProviderCredentialUpdate = Partial<
  Pick<
    ProviderCredential,
    | "display_name"
    | "description"
    | "endpoint"
    | "deployment"
    | "embeddings_model"
    | "api_version"
    | "auth_method"
    | "secret_name"
    | "has_secret"
    | "metadata"
    | "is_enabled"
  >
>;

type ProviderCredentialListResponse = {
  items: ProviderCredential[];
};

const parseErrorBody = async (response: Response): Promise<string> => {
  try {
    const payload = (await response.json()) as { detail?: string; message?: string };
    return payload.detail || payload.message || `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
};

const requestJson = async <T>(path: string, init: RequestInit): Promise<T> => {
  const config = chatApiRuntimeConfig();
  const method = init.method || "GET";
  const url = `${config.baseUrl}${path}`;

  consoleLogger.info("Sending provider credentials API request", { method, path, url });

  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (error) {
    consoleLogger.error("Provider credentials API request failed", { method, path, url }, error);
    throw new ApiRequestError(
      "network",
      "Network request failed. Check API availability, CORS, and URL/protocol."
    );
  }

  if (!response.ok) {
    const detail = await parseErrorBody(response);
    throw new ApiRequestError("http", detail, response.status);
  }

  return (await response.json()) as T;
};

export const listProviderCredentials = async (includeDeleted = false): Promise<ProviderCredential[]> => {
  const config = chatApiRuntimeConfig();
  const params = includeDeleted ? "?include_deleted=true" : "";
  const response = await requestJson<ProviderCredentialListResponse>(`/v1/provider-credentials${params}`, {
    method: "GET",
    headers: {
      "x-api-key": config.apiKey
    }
  });
  return response.items;
};

export const updateProviderCredential = async (
  providerKey: string,
  input: ProviderCredentialUpdate
): Promise<ProviderCredential> => {
  const config = chatApiRuntimeConfig();
  return requestJson<ProviderCredential>(`/v1/provider-credentials/${encodeURIComponent(providerKey)}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": config.apiKey
    },
    body: JSON.stringify(input)
  });
};

export const softDeleteProviderCredential = async (
  providerKey: string
): Promise<ProviderCredential> => {
  const config = chatApiRuntimeConfig();
  return requestJson<ProviderCredential>(`/v1/provider-credentials/${encodeURIComponent(providerKey)}`, {
    method: "DELETE",
    headers: {
      "x-api-key": config.apiKey
    }
  });
};
