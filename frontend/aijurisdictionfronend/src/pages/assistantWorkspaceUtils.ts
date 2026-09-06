import type { CaseRecord } from "../state/CaseProvider";

export const caseThreadKey = (activeCase: CaseRecord | null): string => {
  if (!activeCase) {
    return "assistant-no-case";
  }
  const historyKey = activeCase.interactionHistory
    .map((interaction) => [
      interaction.id,
      interaction.createdAt,
      interaction.message.length,
      interaction.presentation?.schema_version ?? 0,
      interaction.presentation?.renderer_id ?? "none"
    ].join(":"))
    .join("|");
  return `${activeCase.id}:${historyKey}`;
};
