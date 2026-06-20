import { consoleLogger } from "../logging/consoleLogger";

const DEFAULT_API_BASE_URL =
  "https://api-juris-dev.victoriousdesert-e45eec11.westeurope.azurecontainerapps.io";
const DEFAULT_API_KEY = "aijuris";
const DEFAULT_COUNTRY = "SK";
const DEFAULT_LANGUAGE = "en";

export type ChatMessageRole = "user" | "assistant" | "system";

export type ChatSession = {
  id: string;
  user_id: string | null;
  case_id: string | null;
  country: string;
  language: string | null;
  discussion_type: "advice" | "court";
  state: string;
  created_at: string;
};

export type ChatMessage = {
  id: string;
  session_id: string;
  role: ChatMessageRole;
  content: string;
  agent_name: string | null;
  created_at: string;
};

export type CreateChatSessionInput = {
  userId?: string;
  caseId?: string;
  country?: string;
  language?: string;
  discussionType?: "advice" | "court";
};

export type ReplyToSessionInput = {
  sessionId: string;
  content: string;
};

export class ApiRequestError extends Error {
  kind: "network" | "http";
  status?: number;

  constructor(kind: "network" | "http", message: string, status?: number) {
    super(message);
    this.name = "ApiRequestError";
    this.kind = kind;
    this.status = status;
  }
}

type RuntimeApiConfig = {
  baseUrl: string;
  apiKey: string;
  country: string;
  language: string;
};

const resolveApiConfig = (): RuntimeApiConfig => {
  const baseUrl = import.meta.env.VITE_API_BASE_URL?.trim() || DEFAULT_API_BASE_URL;
  const apiKey = import.meta.env.VITE_API_KEY?.trim() || DEFAULT_API_KEY;
  const country = import.meta.env.VITE_API_COUNTRY?.trim() || DEFAULT_COUNTRY;
  const language = import.meta.env.VITE_API_LANGUAGE?.trim() || DEFAULT_LANGUAGE;
  return {
    baseUrl: baseUrl.replace(/\/+$/, ""),
    apiKey,
    country,
    language
  };
};

const parseErrorBody = async (response: Response): Promise<string> => {
  try {
    const payload = (await response.json()) as { detail?: string; message?: string };
    return payload.detail || payload.message || `HTTP ${response.status}`;
  } catch {
    try {
      const textPayload = (await response.text()).trim();
      return textPayload || `HTTP ${response.status}`;
    } catch {
      return `HTTP ${response.status}`;
    }
  }
};

const requestJson = async <T>(path: string, init: RequestInit): Promise<T> => {
  const config = resolveApiConfig();
  const url = `${config.baseUrl}${path}`;
  const method = init.method || "GET";

  consoleLogger.info("Sending API request", {
    method,
    path,
    url
  });

  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (error) {
    consoleLogger.error(
      "API network request failed",
      {
        method,
        path,
        url
      },
      error
    );
    throw new ApiRequestError(
      "network",
      "Network request failed. Check API availability, CORS, and URL/protocol."
    );
  }

  if (!response.ok) {
    const detail = await parseErrorBody(response);
    consoleLogger.warn("API request failed", {
      method,
      path,
      status: response.status,
      detail
    });
    throw new ApiRequestError("http", detail, response.status);
  }

  consoleLogger.info("API request succeeded", {
    method,
    path,
    status: response.status
  });
  return (await response.json()) as T;
};

export const createChatSession = async (input: CreateChatSessionInput = {}): Promise<ChatSession> => {
  const config = resolveApiConfig();
  return requestJson<ChatSession>("/v1/chat/sessions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": config.apiKey
    },
    body: JSON.stringify({
      user_id: input.userId || null,
      case_id: input.caseId || null,
      country: input.country || config.country,
      language: input.language || config.language,
      discussion_type: input.discussionType || "advice"
    })
  });
};

export const replyToSession = async (input: ReplyToSessionInput): Promise<ChatMessage> => {
  const config = resolveApiConfig();
  return requestJson<ChatMessage>(`/v1/chat/sessions/${input.sessionId}/reply`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": config.apiKey
    },
    body: JSON.stringify({
      content: input.content
    })
  });
};

export const chatApiRuntimeConfig = resolveApiConfig;
