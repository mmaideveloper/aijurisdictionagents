const NUMERIC_CHARACTER_REFERENCE = /&#(?:x([0-9a-f]{1,6})|([0-9]{1,7}));/gi;
const INTERNAL_ORCHESTRATOR_NAME = /^LangGraph(?:[A-Za-z0-9_.:-]*)?$/i;
const INTERNAL_ORCHESTRATOR_WORD = /\bLangGraph\b/gi;

export const AI_ORCHESTRATOR_AGENT_LABEL = "AI Orchestrator Agent";

export const decodeNumericCharacterReferences = (value: string): string =>
  value.replace(NUMERIC_CHARACTER_REFERENCE, (reference, hexadecimal: string | undefined, decimal: string | undefined) => {
    const codePoint = Number.parseInt(hexadecimal ?? decimal ?? "", hexadecimal ? 16 : 10);
    if (!Number.isInteger(codePoint) || codePoint < 0 || codePoint > 0x10ffff || (codePoint >= 0xd800 && codePoint <= 0xdfff)) {
      return reference;
    }
    return String.fromCodePoint(codePoint);
  });

export const normalizeAssistantPresentationText = (value: string): string =>
  decodeNumericCharacterReferences(value).replace(INTERNAL_ORCHESTRATOR_WORD, AI_ORCHESTRATOR_AGENT_LABEL);

export const assistantAgentDisplayName = (agentName: string | null | undefined, fallback: string): string => {
  const normalized = agentName?.trim() ?? "";
  if (!normalized) {
    return fallback;
  }
  return INTERNAL_ORCHESTRATOR_NAME.test(normalized) ? AI_ORCHESTRATOR_AGENT_LABEL : normalized;
};
