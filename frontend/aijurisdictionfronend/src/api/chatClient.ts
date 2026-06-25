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

export type StreamSessionInput = {
  sessionId: string;
  instruction: string;
  signal?: AbortSignal;
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
        "x-api-key": config.apiKey
      },
      body: JSON.stringify({
        instruction: input.instruction,
        user_simulation_mode: "ReadUser"
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
    const detail = await parseErrorBody(response);
    consoleLogger.warn("API stream request failed", {
      path,
      status: response.status,
      detail
    });
    throw new ApiRequestError("http", detail, response.status);
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
