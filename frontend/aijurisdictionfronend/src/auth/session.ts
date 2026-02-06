const AUTH_SESSION_STORAGE_KEY = "aijurisdiction.auth.session";

export type AuthProvider = "google" | "x";

export interface UserSession {
  id: string;
  name: string;
  avatarUrl?: string;
  provider: AuthProvider;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function isAuthProvider(value: string): value is AuthProvider {
  return value === "google" || value === "x";
}

function isUserSession(value: unknown): value is UserSession {
  if (!isRecord(value)) {
    return false;
  }

  if (
    typeof value.id !== "string" ||
    typeof value.name !== "string" ||
    typeof value.provider !== "string"
  ) {
    return false;
  }

  if (!isAuthProvider(value.provider)) {
    return false;
  }

  if (
    "avatarUrl" in value &&
    value.avatarUrl !== undefined &&
    typeof value.avatarUrl !== "string"
  ) {
    return false;
  }

  return true;
}

export function getSession(): UserSession | null {
  if (typeof window === "undefined") {
    return null;
  }

  const rawSession = window.localStorage.getItem(AUTH_SESSION_STORAGE_KEY);
  if (!rawSession) {
    return null;
  }

  try {
    const parsedSession: unknown = JSON.parse(rawSession);
    if (!isUserSession(parsedSession)) {
      window.localStorage.removeItem(AUTH_SESSION_STORAGE_KEY);
      return null;
    }
    return parsedSession;
  } catch {
    window.localStorage.removeItem(AUTH_SESSION_STORAGE_KEY);
    return null;
  }
}

export function setSession(session: UserSession): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(AUTH_SESSION_STORAGE_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(AUTH_SESSION_STORAGE_KEY);
}
