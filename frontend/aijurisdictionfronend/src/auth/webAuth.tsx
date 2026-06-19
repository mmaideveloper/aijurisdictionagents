import React from "react";
import { chatApiRuntimeConfig } from "../api/chatClient";

const AUTH_SESSION_KEY = "jurisdigta.web.auth.user.v1";

export interface AuthUser {
  userId: string;
  phoneNumber?: string;
  firstName?: string;
  lastName?: string;
  email: string;
  name: string;
  role?: string;
  accountCreatedAt?: string;
}

interface ApiUserProfile {
  user_id: string;
  phone_number?: string | null;
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  full_name: string;
}

export interface AuthState {
  isAuthenticated: boolean;
  user: AuthUser | null;
  isAuthLoading: boolean;
}

export interface AuthContextValue extends AuthState {
  signIn: (email: string, password: string) => Promise<boolean>;
  signOut: () => void;
}

const AuthContext = React.createContext<AuthContextValue | undefined>(undefined);

export function apiProfileToAuthUser(profile: ApiUserProfile): AuthUser {
  const firstName = profile.first_name?.trim() || undefined;
  const lastName = profile.last_name?.trim() || undefined;
  const fullName = profile.full_name?.trim();
  const fallbackName = [firstName, lastName].filter(Boolean).join(" ").trim();

  return {
    userId: profile.user_id,
    phoneNumber: profile.phone_number?.trim() || undefined,
    email: profile.email,
    firstName,
    lastName,
    name: fullName || fallbackName || profile.email,
    role: "JurisDigta user"
  };
}

async function signInWithApi(email: string, password: string): Promise<AuthUser | null> {
  const config = chatApiRuntimeConfig();
  const response = await fetch(`${config.baseUrl}/v1/users/sign-in`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": config.apiKey
    },
    body: JSON.stringify({ email, password })
  });

  if (response.status === 401) {
    return null;
  }
  if (!response.ok) {
    throw new Error(await parseAuthError(response));
  }

  return apiProfileToAuthUser((await response.json()) as ApiUserProfile);
}

async function parseAuthError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string; message?: string };
    return payload.detail || payload.message || `Sign-in failed with HTTP ${response.status}`;
  } catch {
    return `Sign-in failed with HTTP ${response.status}`;
  }
}

function readStoredUser(): AuthUser | null {
  try {
    const raw = window.sessionStorage.getItem(AUTH_SESSION_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as AuthUser;
    if (!parsed.userId || !parsed.email || !parsed.name) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function writeStoredUser(user: AuthUser | null): void {
  try {
    if (user) {
      window.sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(user));
      return;
    }
    window.sessionStorage.removeItem(AUTH_SESSION_KEY);
  } catch {
    // Session storage is a convenience cache. Auth still works in memory.
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<AuthState>(() => {
    const user = readStoredUser();
    return {
      isAuthenticated: Boolean(user),
      user,
      isAuthLoading: false
    };
  });

  const signIn = React.useCallback(async (email: string, password: string) => {
    const user = await signInWithApi(email, password);
    if (!user) {
      writeStoredUser(null);
      setState({ isAuthenticated: false, user: null, isAuthLoading: false });
      return false;
    }

    writeStoredUser(user);
    setState({ isAuthenticated: true, user, isAuthLoading: false });
    return true;
  }, []);

  const signOut = React.useCallback(() => {
    writeStoredUser(null);
    setState({ isAuthenticated: false, user: null, isAuthLoading: false });
  }, []);

  const value = React.useMemo(
    () => ({
      ...state,
      signIn,
      signOut
    }),
    [state, signIn, signOut]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = React.useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider.");
  }
  return context;
}
