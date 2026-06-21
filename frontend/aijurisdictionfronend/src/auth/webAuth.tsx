import React from "react";
import { chatApiRuntimeConfig } from "../api/chatClient";

const AUTH_SESSION_KEY = "jurisdigta.web.auth.user.v1";
const AUTH_DEVICE_KEY = "jurisdigta.web.auth.device.v1";

export interface AuthUser {
  userId: string;
  phoneNumber?: string;
  firstName?: string;
  lastName?: string;
  email: string;
  name: string;
  address?: string;
  city?: string;
  country?: string;
  zipCode?: string;
  taxNumber?: string;
  identityCardNumber?: string;
  dateOfBirth?: string;
  socialSecurityNumber?: string;
  dataProcessingConsentAt?: string;
  dataProcessingConsentVersion?: string;
  mcpApiKeyExpiresAt?: string;
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
  address?: string | null;
  city?: string | null;
  country?: string | null;
  zip_code?: string | null;
  tax_number?: string | null;
  identity_card_number?: string | null;
  date_of_birth?: string | null;
  social_security_number?: string | null;
  data_processing_consent_at?: string | null;
  data_processing_consent_version?: string | null;
  mcp_api_key_expires_at?: string | null;
  created_at?: string | null;
}

export interface AuthState {
  isAuthenticated: boolean;
  user: AuthUser | null;
  isAuthLoading: boolean;
}

export interface AuthContextValue extends AuthState {
  signIn: (email: string, password: string, verificationCode?: string) => Promise<AuthSignInResult>;
  sendSignUpCode: (email: string) => Promise<void>;
  signUp: (input: SignUpInput) => Promise<boolean>;
  updateProfile: (input: ProfileUpdateInput) => Promise<AuthUser>;
  sendEmailChangeCode: (email: string) => Promise<void>;
  completeEmailChange: (email: string, verificationCode: string) => Promise<AuthUser>;
  signOut: () => void;
}

export type AuthSignInResult = "signed_in" | "otp_required" | "invalid_credentials";

export interface SignUpInput {
  phoneNumber: string;
  email: string;
  password: string;
  verificationCode: string;
}

export interface ProfileUpdateInput {
  phoneNumber: string;
  firstName?: string;
  lastName?: string;
  address?: string;
  city?: string;
  country?: string;
  zipCode?: string;
  taxNumber?: string;
  identityCardNumber?: string;
  dateOfBirth?: string;
  socialSecurityNumber?: string;
  password?: string;
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
    address: profile.address?.trim() || undefined,
    city: profile.city?.trim() || undefined,
    country: profile.country?.trim() || undefined,
    zipCode: profile.zip_code?.trim() || undefined,
    taxNumber: profile.tax_number?.trim() || undefined,
    identityCardNumber: profile.identity_card_number?.trim() || undefined,
    dateOfBirth: profile.date_of_birth?.trim() || undefined,
    socialSecurityNumber: profile.social_security_number?.trim() || undefined,
    dataProcessingConsentAt: profile.data_processing_consent_at?.trim() || undefined,
    dataProcessingConsentVersion: profile.data_processing_consent_version?.trim() || undefined,
    mcpApiKeyExpiresAt: profile.mcp_api_key_expires_at?.trim() || undefined,
    accountCreatedAt: profile.created_at?.trim() || undefined,
    role: "JurisDigta user"
  };
}

interface SignInApiResult {
  status: AuthSignInResult;
  user?: AuthUser;
}

async function signInWithApi(email: string, password: string, verificationCode?: string): Promise<SignInApiResult> {
  const config = chatApiRuntimeConfig();
  const response = await fetch(`${config.baseUrl}/v1/users/sign-in`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": config.apiKey
    },
    body: JSON.stringify({
      email,
      password,
      device_id: getOrCreateDeviceId(),
      verification_code: verificationCode?.trim() || undefined
    })
  });

  if (response.status === 401) {
    return { status: "invalid_credentials" };
  }
  if (response.status === 428) {
    return { status: "otp_required" };
  }
  if (!response.ok) {
    throw new Error(await parseAuthError(response));
  }

  return { status: "signed_in", user: apiProfileToAuthUser((await response.json()) as ApiUserProfile) };
}

async function sendSignUpCodeWithApi(email: string): Promise<void> {
  const config = chatApiRuntimeConfig();
  const response = await fetch(`${config.baseUrl}/v1/users/sign-up/send-code`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": config.apiKey
    },
    body: JSON.stringify({ email })
  });

  if (!response.ok) {
    throw new Error(await parseAuthError(response));
  }
}

async function signUpWithApi(input: SignUpInput): Promise<AuthUser> {
  const config = chatApiRuntimeConfig();
  const response = await fetch(`${config.baseUrl}/v1/users/sign-up/complete`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": config.apiKey
    },
    body: JSON.stringify({
      phone_number: input.phoneNumber,
      email: input.email,
      password: input.password,
      verification_code: input.verificationCode,
      data_processing_consent_accepted: true,
      data_processing_consent_version: "web-sign-up-v1"
    })
  });

  if (!response.ok) {
    throw new Error(await parseAuthError(response));
  }

  return apiProfileToAuthUser((await response.json()) as ApiUserProfile);
}

async function updateProfileWithApi(userId: string, input: ProfileUpdateInput): Promise<AuthUser> {
  const config = chatApiRuntimeConfig();
  const response = await fetch(`${config.baseUrl}/v1/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": config.apiKey
    },
    body: JSON.stringify({
      phone_number: input.phoneNumber,
      password: input.password || undefined,
      first_name: input.firstName || null,
      last_name: input.lastName || null,
      address: input.address || null,
      city: input.city || null,
      country: input.country || null,
      zip_code: input.zipCode || null,
      tax_number: input.taxNumber || null,
      identity_card_number: input.identityCardNumber || null,
      date_of_birth: input.dateOfBirth || null,
      social_security_number: input.socialSecurityNumber || null
    })
  });

  if (!response.ok) {
    throw new Error(await parseAuthError(response));
  }

  return apiProfileToAuthUser((await response.json()) as ApiUserProfile);
}

async function sendEmailChangeCodeWithApi(userId: string, email: string): Promise<void> {
  const config = chatApiRuntimeConfig();
  const response = await fetch(`${config.baseUrl}/v1/users/${encodeURIComponent(userId)}/email-change/send-code`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": config.apiKey
    },
    body: JSON.stringify({ email })
  });

  if (!response.ok) {
    throw new Error(await parseAuthError(response));
  }
}

async function completeEmailChangeWithApi(
  userId: string,
  email: string,
  verificationCode: string
): Promise<AuthUser> {
  const config = chatApiRuntimeConfig();
  const response = await fetch(`${config.baseUrl}/v1/users/${encodeURIComponent(userId)}/email-change/complete`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": config.apiKey
    },
    body: JSON.stringify({ email, verification_code: verificationCode })
  });

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

function getOrCreateDeviceId(): string {
  try {
    const existing = window.localStorage.getItem(AUTH_DEVICE_KEY);
    if (existing) {
      return existing;
    }
    const generated =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `web-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    window.localStorage.setItem(AUTH_DEVICE_KEY, generated);
    return generated;
  } catch {
    return "web-session";
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

  const signIn = React.useCallback(async (email: string, password: string, verificationCode?: string) => {
    const result = await signInWithApi(email, password, verificationCode);
    if (result.status === "invalid_credentials") {
      writeStoredUser(null);
      setState({ isAuthenticated: false, user: null, isAuthLoading: false });
      return "invalid_credentials";
    }
    if (result.status === "otp_required") {
      return "otp_required";
    }

    const user = result.user;
    if (!user) {
      throw new Error("Missing authenticated user profile.");
    }
    writeStoredUser(user);
    setState({ isAuthenticated: true, user, isAuthLoading: false });
    return "signed_in";
  }, []);

  const sendSignUpCode = React.useCallback(async (email: string) => {
    await sendSignUpCodeWithApi(email);
  }, []);

  const signUp = React.useCallback(async (input: SignUpInput) => {
    const user = await signUpWithApi(input);
    writeStoredUser(user);
    setState({ isAuthenticated: true, user, isAuthLoading: false });
    return true;
  }, []);

  const updateProfile = React.useCallback(
    async (input: ProfileUpdateInput) => {
      if (!state.user) {
        throw new Error("Cannot update profile without an authenticated user.");
      }
      const user = await updateProfileWithApi(state.user.userId, input);
      writeStoredUser(user);
      setState({ isAuthenticated: true, user, isAuthLoading: false });
      return user;
    },
    [state.user]
  );

  const sendEmailChangeCode = React.useCallback(
    async (email: string) => {
      if (!state.user) {
        throw new Error("Cannot change email without an authenticated user.");
      }
      await sendEmailChangeCodeWithApi(state.user.userId, email);
    },
    [state.user]
  );

  const completeEmailChange = React.useCallback(
    async (email: string, verificationCode: string) => {
      if (!state.user) {
        throw new Error("Cannot change email without an authenticated user.");
      }
      const user = await completeEmailChangeWithApi(state.user.userId, email, verificationCode);
      writeStoredUser(user);
      setState({ isAuthenticated: true, user, isAuthLoading: false });
      return user;
    },
    [state.user]
  );

  const signOut = React.useCallback(() => {
    writeStoredUser(null);
    setState({ isAuthenticated: false, user: null, isAuthLoading: false });
  }, []);

  const value = React.useMemo(
    () => ({
      ...state,
      signIn,
      sendSignUpCode,
      signUp,
      updateProfile,
      sendEmailChangeCode,
      completeEmailChange,
      signOut
    }),
    [state, signIn, sendSignUpCode, signUp, updateProfile, sendEmailChangeCode, completeEmailChange, signOut]
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
