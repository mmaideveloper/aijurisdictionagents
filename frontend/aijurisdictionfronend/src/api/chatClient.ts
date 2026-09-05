import { consoleLogger } from "../logging/consoleLogger";
import {
  correlationHeaders,
  createSessionCorrelationId,
  setActiveSessionCorrelationId
} from "./correlation";
import type { PresentationBlock } from "../presentation";

const DEFAULT_API_BASE_URL =
  "https://api-juris-dev.victoriousdesert-e45eec11.westeurope.azurecontainerapps.io";
const DEFAULT_API_KEY = "aijuris";
const DEFAULT_COUNTRY = "SK";
const DEFAULT_LANGUAGE = "en";
const DEFAULT_CHAT_MODEL_LABEL = "Azure Foundry model";

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
  correlation_id?: string;
};

export type ChatMessage = {
  id: string;
  session_id: string;
  role: ChatMessageRole;
  content: string;
  agent_name: string | null;
  created_at: string;
  citations?: Array<Record<string, unknown>>;
  presentation?: PresentationBlock;
};

export type EffectiveModelRoute = {
  plan_code: string;
  route_type: string;
  provider: string;
  provider_display_name: string;
  model: string;
  model_profile_id: string;
  is_local: boolean;
  is_external: boolean;
  label: string;
};

export type SelectableModelProfile = {
  model_profile_id: string;
  provider: string;
  provider_display_name: string;
  model: string;
  label: string;
  is_local: boolean;
  is_external: boolean;
  eu_data_zone_capable: boolean;
  context_window_tokens: number;
};

export type SelectableModelProfiles = {
  eligible: boolean;
  profiles: SelectableModelProfile[];
};

export type SelectableModelProfileRequest = {
  userId?: string;
  userEmail?: string;
};

export type CreateChatSessionInput = {
  userId?: string;
  caseId?: string;
  country?: string;
  language?: string;
  discussionType?: "advice" | "court";
  modelProfileId?: string;
  correlationId?: string;
};

export type ReplyToSessionInput = {
  sessionId: string;
  content: string;
  userId?: string;
  userEmail?: string;
  modelProfileId?: string;
};

export type StreamSessionInput = {
  sessionId: string;
  instruction: string;
  userId?: string;
  userEmail?: string;
  modelProfileId?: string;
  signal?: AbortSignal;
  correlationId: string;
};

export type ChatStreamEvent =
  | {
      event: "message";
      data: ChatMessage;
    }
  | {
      event: "processing";
      data: {
        stage?: string;
        message?: string;
        details?: unknown;
      };
    }
  | {
      event: "waiting_for_reply";
      data: {
        session_id?: string;
        mode?: string;
        message?: string;
      };
    }
  | {
      event: "result" | "done" | "error";
      data: Record<string, unknown>;
    };

export class ApiRequestError extends Error {
  kind: "network" | "http";
  status?: number;
  code?: string;
  params?: ApiErrorParams;

  constructor(
    kind: "network" | "http",
    message: string,
    status?: number,
    metadata: { code?: string; params?: ApiErrorParams } = {}
  ) {
    super(message);
    this.name = "ApiRequestError";
    this.kind = kind;
    this.status = status;
    this.code = metadata.code;
    this.params = metadata.params;
  }
}

export type ApiErrorParams = Record<string, string | number | boolean | null | undefined>;

type ParsedApiError = {
  message: string;
  code?: string;
  params?: ApiErrorParams;
};

type RuntimeApiConfig = {
  baseUrl: string;
  apiKey: string;
  country: string;
  language: string;
  chatModelLabel: string;
};

const resolveApiConfig = (): RuntimeApiConfig => {
  const baseUrl = import.meta.env.VITE_API_BASE_URL?.trim() || DEFAULT_API_BASE_URL;
  const apiKey = import.meta.env.VITE_API_KEY?.trim() || DEFAULT_API_KEY;
  const country = import.meta.env.VITE_API_COUNTRY?.trim() || DEFAULT_COUNTRY;
  const language = import.meta.env.VITE_API_LANGUAGE?.trim() || DEFAULT_LANGUAGE;
  const chatModelLabel = sanitizePublicModelLabel(
    import.meta.env.VITE_CHAT_MODEL_LABEL?.trim() || DEFAULT_CHAT_MODEL_LABEL
  );
  return {
    baseUrl: baseUrl.replace(/\/+$/, ""),
    apiKey,
    country,
    language,
    chatModelLabel
  };
};

const sanitizePublicModelLabel = (label: string): string => {
  const trimmed = label.trim();
  const looksLikeSecret =
    /^sk-[A-Za-z0-9_-]{12,}/.test(trimmed) ||
    /^gh[pousr]_[A-Za-z0-9_]{12,}/.test(trimmed) ||
    /^eyJ[A-Za-z0-9_-]+\./.test(trimmed) ||
    trimmed.includes("://") ||
    trimmed.includes("=");
  if (!trimmed || looksLikeSecret) {
    return DEFAULT_CHAT_MODEL_LABEL;
  }
  return trimmed.slice(0, 80);
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const normalizeApiErrorPayload = (payload: unknown, status: number): ParsedApiError => {
  if (!isRecord(payload)) {
    return { message: typeof payload === "string" && payload.trim() ? payload : `HTTP ${status}` };
  }

  const detail = payload.detail;
  if (isRecord(detail)) {
    const message = typeof detail.message === "string" && detail.message.trim() ? detail.message : `HTTP ${status}`;
    const code = typeof detail.code === "string" && detail.code.trim() ? detail.code : undefined;
    const params = isRecord(detail.params) ? (detail.params as ApiErrorParams) : undefined;
    return { message, code, params };
  }

  if (typeof detail === "string" && detail.trim()) {
    return { message: detail };
  }

  if (typeof payload.message === "string" && payload.message.trim()) {
    return { message: payload.message };
  }

  return { message: `HTTP ${status}` };
};

export const parseApiErrorResponse = async (response: Response): Promise<ParsedApiError> => {
  try {
    return normalizeApiErrorPayload(await response.json(), response.status);
  } catch {
    try {
      const textPayload = (await response.text()).trim();
      return { message: textPayload || `HTTP ${response.status}` };
    } catch {
      return { message: `HTTP ${response.status}` };
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
    response = await fetch(url, {
      ...init,
      headers: { ...correlationHeaders(), ...(init.headers ?? {}) }
    });
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
    const detail = await parseApiErrorResponse(response);
    consoleLogger.warn("API request failed", {
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

  consoleLogger.info("API request succeeded", {
    method,
    path,
    status: response.status
  });
  return (await response.json()) as T;
};

export const createChatSession = async (input: CreateChatSessionInput = {}): Promise<ChatSession> => {
  const config = resolveApiConfig();
  const session = await requestJson<ChatSession>("/v1/chat/sessions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": config.apiKey,
      ...correlationHeaders(input.correlationId)
    },
    body: JSON.stringify({
      user_id: input.userId || null,
      case_id: input.caseId || null,
      country: input.country || config.country,
      language: input.language || config.language,
      discussion_type: input.discussionType || "advice",
      model_profile_id: input.modelProfileId?.trim() || null,
      correlation_id: input.correlationId?.trim() || null
    })
  });
  const resolvedCorrelationId =
    session.correlation_id?.trim() || input.correlationId?.trim() || createSessionCorrelationId();
  setActiveSessionCorrelationId(resolvedCorrelationId);
  return { ...session, correlation_id: resolvedCorrelationId };
};

export const replyToSession = async (input: ReplyToSessionInput): Promise<ChatMessage> => {
  const config = resolveApiConfig();
  return requestJson<ChatMessage>(`/v1/chat/sessions/${input.sessionId}/reply`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": config.apiKey,
      ...correlationHeaders()
    },
    body: JSON.stringify({
      content: input.content,
      user_id: input.userId?.trim() || null,
      user_email: input.userEmail?.trim() || null,
      model_profile_id: input.modelProfileId?.trim() || null
    })
  });
};

export const fetchEffectiveModelRoute = async (userId?: string): Promise<EffectiveModelRoute> => {
  const config = resolveApiConfig();
  const params = new URLSearchParams({ task_type: "chat_reply" });
  if (userId?.trim()) {
    params.set("user_id", userId.trim());
  }
  return requestJson<EffectiveModelRoute>(`/v1/model-routing/effective?${params.toString()}`, {
    method: "GET",
    headers: {
      "x-api-key": config.apiKey
    }
  });
};

export const fetchSelectableModelProfiles = async ({
  userId,
  userEmail
}: SelectableModelProfileRequest): Promise<SelectableModelProfiles> => {
  const config = resolveApiConfig();
  const params = new URLSearchParams();
  if (userId?.trim()) {
    params.set("user_id", userId.trim());
  }
  if (userEmail?.trim()) {
    params.set("user_email", userEmail.trim());
  }
  return requestJson<SelectableModelProfiles>(`/v1/model-routing/selectable?${params.toString()}`, {
    method: "GET",
    headers: {
      "x-api-key": config.apiKey
    }
  });
};

const parseSseBlock = (block: string): ChatStreamEvent | null => {
  let eventName = "message";
  const dataLines: string[] = [];

  for (const line of block.split(/\r?\n/)) {
    if (!line.trim() || line.startsWith(":")) {
      continue;
    }
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  return {
    event: eventName,
    data: JSON.parse(dataLines.join("\n")) as Record<string, unknown>
  } as ChatStreamEvent;
};

export async function* streamSession(input: StreamSessionInput): AsyncGenerator<ChatStreamEvent, void> {
  const config = resolveApiConfig();
  const path = `/v1/chat/sessions/${input.sessionId}/stream`;
  const url = `${config.baseUrl}${path}`;

  consoleLogger.info("Starting API stream request", {
    method: "POST",
    path,
    url
  });

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": config.apiKey,
        ...correlationHeaders(input.correlationId)
      },
      body: JSON.stringify({
        instruction: input.instruction,
        user_simulation_mode: "ReadUser",
        user_id: input.userId?.trim() || null,
        user_email: input.userEmail?.trim() || null,
        model_profile_id: input.modelProfileId?.trim() || null
      }),
      signal: input.signal
    });
  } catch (error) {
    consoleLogger.error("API stream request failed before response", { path, url }, error);
    throw new ApiRequestError(
      "network",
      "Network request failed. Check API availability, CORS, and URL/protocol."
    );
  }

  if (!response.ok) {
    const detail = await parseApiErrorResponse(response);
    consoleLogger.warn("API stream request failed", {
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

  if (!response.body) {
    throw new ApiRequestError("network", "Streaming body is not available in this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() ?? "";

      for (const block of blocks) {
        const event = parseSseBlock(block);
        if (event) {
          yield event;
        }
      }
    }

    buffer += decoder.decode();
    const trailingEvent = parseSseBlock(buffer);
    if (trailingEvent) {
      yield trailingEvent;
    }
  } finally {
    reader.releaseLock();
  }
}

export const chatApiRuntimeConfig = resolveApiConfig;
