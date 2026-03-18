import React from "react";

export interface MockUser {
  firstName: string;
  lastName: string;
  email: string;
  password: string;
  name: string;
  role?: string;
  accountCreatedAt?: string;
}

export const MOCK_USER: MockUser = {
  firstName: "Admin",
  lastName: "User",
  email: "admin@admin.com",
  password: "admin123",
  name: "Admin User",
  role: "Administrator",
  accountCreatedAt: "2025-01-10"
};

export interface AuthState {
  isAuthenticated: boolean;
  user: Omit<MockUser, "password"> | null;
}

export interface AuthContextValue extends AuthState {
  signIn: (email: string, password: string) => boolean;
  signOut: () => void;
}

export function isValidCredentials(email: string, password: string): boolean {
  return email === MOCK_USER.email && password === MOCK_USER.password;
}

const AuthContext = React.createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<AuthState>({
    isAuthenticated: false,
    user: null
  });

  const signIn = React.useCallback((email: string, password: string) => {
    if (!isValidCredentials(email, password)) {
      setState({ isAuthenticated: false, user: null });
      return false;
    }

    setState({
      isAuthenticated: true,
      user: {
        firstName: MOCK_USER.firstName,
        lastName: MOCK_USER.lastName,
        email: MOCK_USER.email,
        name: MOCK_USER.name,
        role: MOCK_USER.role,
        accountCreatedAt: MOCK_USER.accountCreatedAt
      }
    });
    return true;
  }, []);

  const signOut = React.useCallback(() => {
    setState({ isAuthenticated: false, user: null });
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
