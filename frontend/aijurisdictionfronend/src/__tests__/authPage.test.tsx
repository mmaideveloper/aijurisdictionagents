// @vitest-environment jsdom

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import Auth from "../pages/Auth";

const mockSignIn = vi.fn();
const mockSendSignUpCode = vi.fn();
const mockSignUp = vi.fn();
const mockSignOut = vi.fn();
const mockSendMfaEmailCode = vi.fn();
const mockVerifyMfa = vi.fn();

vi.mock("../auth/webAuth", () => ({
  useAuth: () => ({
    isAuthenticated: false,
    user: null,
    signIn: mockSignIn,
    sendSignUpCode: mockSendSignUpCode,
    signUp: mockSignUp,
    signOut: mockSignOut,
    sendMfaEmailCode: mockSendMfaEmailCode,
    verifyMfa: mockVerifyMfa
  })
}));

const labels: Record<string, string> = {
  authTitle: "Secure access",
  authSubtitle: "Sign in to continue.",
  authEmail: "Email",
  authPassword: "Password",
  authPhone: "Phone",
  authSigningIn: "Signing in",
  authSignIn: "Sign in",
  authApiLoginHint: "Use your API account.",
  authInvalidCredentials: "Invalid email or password.",
  authSignInFailed: "Sign-in failed.",
  authRegisterFailed: "Registration failed.",
  authRegisterMissingFields: "Enter email, password, and phone.",
  authEmailRequired: "Enter email.",
  authOtpCode: "OTP code",
  authOtpSending: "Sending OTP",
  authLoginOtpSent: "Login OTP sent.",
  authRegisterSendOtp: "Send registration OTP",
  authRegisterOtpSent: "Registration OTP sent.",
  authRegisterOtpFailed: "Could not send registration OTP.",
  authRegisterOtpRequired: "Registration OTP required.",
  authSignedIn: "Signed in.",
  authRegistered: "Account created.",
  authSignedInAs: "Signed in as",
  authResetSession: "Reset session",
  authMfaRequired: "MFA verification is required.",
  authMfaMethod: "MFA method",
  authMfaEmail: "Email OTP",
  authMfaTotp: "Authenticator app",
  authMfaEmailCode: "Email code",
  authMfaTotpCode: "Authenticator code",
  authMfaVerify: "Verify MFA",
  authMfaInvalid: "Invalid MFA code.",
  authMfaEmailSent: "Email OTP code sent.",
  authCreateTitle: "New account",
  authCreateBody: "Create account text.",
  authRegister: "Register",
  authRegistering: "Registering",
  commonUser: "User"
};

vi.mock("../components/LanguageProvider", () => ({
  useLanguage: () => ({
    t: (key: string) => labels[key] ?? key
  })
}));

function renderAuthPage() {
  const PathIndicator = () => {
    const location = useLocation();
    return <div data-testid="current-path">{location.pathname}</div>;
  };

  return render(
    <MemoryRouter initialEntries={["/auth"]}>
      <Auth />
      <PathIndicator />
    </MemoryRouter>
  );
}

describe("Auth page", () => {
  beforeEach(() => {
    mockSignIn.mockReset();
    mockSendSignUpCode.mockReset();
    mockSignUp.mockReset();
    mockSignOut.mockReset();
    mockSendMfaEmailCode.mockReset();
    mockVerifyMfa.mockReset();
    mockSignIn.mockResolvedValue("signed_in");
    mockSendSignUpCode.mockResolvedValue(undefined);
    mockSignUp.mockResolvedValue(true);
    mockSendMfaEmailCode.mockResolvedValue(undefined);
    mockVerifyMfa.mockResolvedValue(true);
  });

  afterEach(() => {
    cleanup();
  });

  it("opens the assistant workspace after successful login", async () => {
    const user = userEvent.setup();
    renderAuthPage();

    await user.type(screen.getByLabelText("Email"), "local.dev@jurisdigta.test");
    await user.type(screen.getByLabelText("Password"), "LocalTest123!");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(screen.getByTestId("current-path").textContent).toBe("/app/assistant");
    });
    expect(mockSignIn).toHaveBeenCalledWith("local.dev@jurisdigta.test", "LocalTest123!", "");
  });

  it("asks for OTP when login requires a daily email code", async () => {
    const user = userEvent.setup();
    mockSignIn.mockResolvedValueOnce("otp_required").mockResolvedValueOnce("signed_in");
    renderAuthPage();

    await user.type(screen.getByLabelText("Email"), "local.dev@jurisdigta.test");
    await user.type(screen.getByLabelText("Password"), "LocalTest123!");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(screen.getByText("Login OTP sent.")).toBeDefined();
    const loginOtpInput = screen.getAllByLabelText("OTP code")[0];
    expect(loginOtpInput).toBeDefined();
    await user.type(loginOtpInput as HTMLElement, "654321");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(screen.getByTestId("current-path").textContent).toBe("/app/assistant");
    });
    expect(mockSignIn).toHaveBeenLastCalledWith("local.dev@jurisdigta.test", "LocalTest123!", "654321");
  });

  it("shows authenticator MFA when the account has TOTP enabled", async () => {
    const user = userEvent.setup();
    mockSignIn.mockResolvedValueOnce({
      status: "mfa_required",
      challenge: {
        mfaRequired: true,
        mfaToken: "mfa-token",
        userId: "user-1",
        email: "local.dev@jurisdigta.test",
        methods: ["email", "totp"],
        reuseWindowHours: 0
      }
    });
    renderAuthPage();

    await user.type(screen.getByLabelText("Email"), "local.dev@jurisdigta.test");
    await user.type(screen.getByLabelText("Password"), "LocalTest123!");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(screen.getByLabelText("MFA method")).toBeDefined();
    expect(screen.getByLabelText("Authenticator code")).toBeDefined();
    await user.type(screen.getByLabelText("Authenticator code"), "123456");
    await user.click(screen.getByRole("button", { name: "Verify MFA" }));

    await waitFor(() => {
      expect(mockVerifyMfa).toHaveBeenCalledWith("mfa-token", "totp", "123456");
    });
    expect(screen.getByTestId("current-path").textContent).toBe("/app/assistant");
  });

  it("creates an account and opens the assistant workspace", async () => {
    const user = userEvent.setup();
    renderAuthPage();

    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.type(screen.getByLabelText("Password"), "Secret123!");
    await user.type(screen.getByLabelText("Phone"), "+421900123456");
    await user.click(screen.getByRole("button", { name: "Send registration OTP" }));
    await user.type(screen.getByLabelText("OTP code"), "123456");
    await user.click(screen.getByRole("button", { name: "Register" }));

    await waitFor(() => {
      expect(screen.getByTestId("current-path").textContent).toBe("/app/assistant");
    });
    expect(mockSignUp).toHaveBeenCalledWith({
      phoneNumber: "+421900123456",
      email: "new@example.com",
      password: "Secret123!",
      verificationCode: "123456"
    });
    expect(mockSendSignUpCode).toHaveBeenCalledWith("new@example.com");
  });

  it("requires registration OTP before account creation", async () => {
    const user = userEvent.setup();
    renderAuthPage();

    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.type(screen.getByLabelText("Password"), "Secret123!");
    await user.type(screen.getByLabelText("Phone"), "+421900123456");
    await user.click(screen.getByRole("button", { name: "Register" }));

    expect(screen.getByRole("alert").textContent).toBe("Registration OTP required.");
    expect(mockSignUp).not.toHaveBeenCalled();
  });

  it("requires email, password, and phone before registration", async () => {
    const user = userEvent.setup();
    renderAuthPage();

    await user.click(screen.getByRole("button", { name: "Register" }));

    expect(screen.getByRole("alert").textContent).toBe("Enter email, password, and phone.");
    expect(mockSignUp).not.toHaveBeenCalled();
  });
});
