export type CaseRole = "AI Lawyer" | "AI Judge" | "Opposing Counsel";

export const AVAILABLE_CASE_ROLES: readonly CaseRole[] = ["AI Lawyer"];

export const isCaseRoleAvailable = (role: CaseRole): boolean => AVAILABLE_CASE_ROLES.includes(role);

export const normalizeCaseRole = (role: unknown): CaseRole => {
  if (role === "AI Lawyer" || role === "AI Judge" || role === "Opposing Counsel") {
    return isCaseRoleAvailable(role) ? role : "AI Lawyer";
  }
  return "AI Lawyer";
};
