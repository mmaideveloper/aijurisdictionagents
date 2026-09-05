export const PRESENTATION_RENDERER_IDS = [
  "result_card",
  "key_value_table",
  "data_table",
  "notice",
  "document_preview",
  "text",
  "sanitized_json",
  "action_link"
] as const;

export type PresentationRendererId = (typeof PRESENTATION_RENDERER_IDS)[number];

export type PresentationBlock = {
  schema_version: 1;
  renderer_id: PresentationRendererId;
  renderer_version: 1;
  data: Record<string, unknown>;
  fallback_text: string;
  citations: string[];
  notices: string[];
  selection: {
    policy_id: string;
    reason_code: string;
    explicit_user_request: boolean;
    model_proposal_accepted: boolean;
  };
};

const rendererIds = new Set<string>(PRESENTATION_RENDERER_IDS);
const MAX_PRESENTATION_BYTES = 128_000;
const MAX_PRESENTATION_ITEMS = 100;
const MAX_PRESENTATION_TEXT = 12_000;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const stringList = (value: unknown): string[] | null => {
  if (!Array.isArray(value) || value.length > MAX_PRESENTATION_ITEMS) {
    return null;
  }
  const strings = value.filter((item): item is string => typeof item === "string");
  if (strings.length !== value.length || strings.some((item) => item.length > 500)) {
    return null;
  }
  return strings;
};

export const normalizePresentationBlock = (value: unknown): PresentationBlock | null => {
  if (!isRecord(value)) {
    return null;
  }
  try {
    if (new TextEncoder().encode(JSON.stringify(value)).length > MAX_PRESENTATION_BYTES) {
      return null;
    }
  } catch {
    return null;
  }
  const selection = value.selection;
  const citations = stringList(value.citations);
  const notices = stringList(value.notices);
  if (
    value.schema_version !== 1 ||
    value.renderer_version !== 1 ||
    typeof value.renderer_id !== "string" ||
    !rendererIds.has(value.renderer_id) ||
    !isRecord(value.data) ||
    typeof value.fallback_text !== "string" ||
    value.fallback_text.length > MAX_PRESENTATION_TEXT ||
    citations === null ||
    notices === null ||
    !isRecord(selection) ||
    typeof selection.policy_id !== "string" ||
    typeof selection.reason_code !== "string" ||
    typeof selection.explicit_user_request !== "boolean" ||
    typeof selection.model_proposal_accepted !== "boolean"
  ) {
    return null;
  }
  return {
    schema_version: 1,
    renderer_id: value.renderer_id as PresentationRendererId,
    renderer_version: 1,
    data: value.data,
    fallback_text: value.fallback_text,
    citations,
    notices,
    selection: {
      policy_id: selection.policy_id,
      reason_code: selection.reason_code,
      explicit_user_request: selection.explicit_user_request,
      model_proposal_accepted: selection.model_proposal_accepted
    }
  };
};

export const displayValue = (value: unknown): string => {
  if (value === null || value === undefined) {
    return "—";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return "—";
  }
};
