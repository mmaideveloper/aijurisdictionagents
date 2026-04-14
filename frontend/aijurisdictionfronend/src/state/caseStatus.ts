import type { TranslationKey } from "../data/translations";
import type { CaseStatus } from "./CaseProvider";

export const caseStatusTranslationKeys: Record<CaseStatus, TranslationKey> = {
  "In progress": "workspaceStatusInProgress",
  "On hold": "workspaceStatusOnHold",
  Scheduled: "workspaceStatusScheduled",
  Completed: "workspaceStatusCompleted"
};
