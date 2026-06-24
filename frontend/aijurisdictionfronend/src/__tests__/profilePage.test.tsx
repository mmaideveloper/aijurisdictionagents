// @vitest-environment jsdom

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Profile from "../pages/Profile";

const authMocks = vi.hoisted(() => ({
  updateProfile: vi.fn(),
  sendEmailChangeCode: vi.fn(),
  completeEmailChange: vi.fn(),
  refreshUser: vi.fn(),
  user: {
    userId: "user-1",
    phoneNumber: "+421900111222",
    firstName: "Admin",
    lastName: "User",
    email: "user@example.com",
    address: "Main Street 1",
    city: "Bratislava",
    country: "SK",
    zipCode: "811 01",
    taxNumber: "12345678",
    identityCardNumber: "AB123456",
    dateOfBirth: "1980-01-02",
    socialSecurityNumber: "800102/1234",
    dataProcessingConsentAt: "2026-06-21T09:12:28+00:00",
    dataProcessingConsentVersion: "web-sign-up-v1",
    mcpApiKeyExpiresAt: "2026-06-22T09:12:28+00:00",
    accountCreatedAt: "2026-06-21T09:12:28+00:00",
    role: "JurisDigta user",
    name: "Admin User",
    mfaTotpEnabled: false
  }
}));

vi.mock("../auth/webAuth", () => ({
  useAuth: () => ({
    user: authMocks.user,
    updateProfile: authMocks.updateProfile,
    sendEmailChangeCode: authMocks.sendEmailChangeCode,
    completeEmailChange: authMocks.completeEmailChange,
    refreshUser: authMocks.refreshUser
  })
}));

vi.mock("../state/CaseProvider", () => ({
  useCases: () => ({
    cases: [
      {
        id: "case-1",
        title: "Keystone Holdings Intake",
        status: "In progress"
      }
    ],
    documents: [
      {
        id: "doc-1",
        originalFilename: "keystone-timeline.pdf",
        caseTitle: "Keystone Holdings Intake",
        sizeLabel: "178 KB"
      }
    ],
    selectCase: vi.fn()
  })
}));

const labels: Record<string, string> = {
  profileTitle: "My Profile",
  profileSubtitle: "Review account details stored in your workspace session.",
  profileOverviewTitle: "Session profile",
  profileOverviewBody: "This data is loaded from the current API-authenticated user.",
  profileDocumentDataReuseNotice:
    "Profile data will be reused automatically when creating legal documents.",
  profileDetailsTitle: "User details",
  profileFieldUserId: "User ID",
  profileFieldFirstName: "First Name",
  profileFieldLastName: "Last Name",
  profileFieldFullName: "Full Name",
  profileFieldEmail: "Email",
  profileFieldPhoneRequired: "Phone number (required)",
  profileFieldAddress: "Address",
  profileFieldCity: "City",
  profileFieldCountry: "Country",
  profileFieldZipCode: "ZIP code",
  profileFieldTaxNumber: "IČO / tax number",
  profileFieldIdentityCardNumber: "Identity card number",
  profileFieldDateOfBirth: "Date of birth",
  profileFieldSocialSecurityNumber: "Birth number / social security number",
  profileFieldDataProcessingConsentAt: "Data processing consent at",
  profileFieldDataProcessingConsentVersion: "Data processing consent version",
  profileFieldMcpApiKeyExpiresAt: "MCP API key expires at",
  profileFieldRole: "Role",
  profileFieldAccountCreated: "Account Created Date",
  profileOpenedCasesTitle: "Opened cases",
  profileOpenedCasesSubtitle: "Jump back into active matters from your profile.",
  profileOpenedCasesEmpty: "No opened cases yet.",
  profileDocumentsTitle: "My Documents",
  profileDocumentsSubtitle: "Uploaded documents from your case intake flow.",
  profileDocumentsEmpty: "No uploaded documents yet.",
  profileDocumentCaseLabel: "Case",
  profileBilling: "Billing cadence",
  pricingMonthly: "Monthly",
  pricingYearly: "Yearly",
  profileCadenceCurrent: "Current cadence",
  profilePlan: "Subscription tier",
  profilePlanSelected: "Selected",
  profileSave: "Save changes",
  profileEdit: "Edit",
  profileSaving: "Saving",
  profileSaveSuccess: "Profile was saved.",
  profileSaveFailed: "Profile save failed.",
  profilePhoneRequired: "Phone number is required.",
  profilePasswordOptional: "New password (optional)",
  profileEmailRequired: "Enter a new email.",
  profileEmailSendCode: "Send OTP code",
  profileEmailSendingCode: "Sending code",
  profileEmailCodeSent: "OTP code sent.",
  profileEmailCodeSendFailed: "Could not send OTP.",
  profileEmailOtpCode: "OTP code for email change",
  profileEmailChangeRequiresCode: "Email change requires OTP code.",
  profileMfaTitle: "Multi-factor authentication",
  profileMfaTotpEnabled: "Authenticator app MFA is enabled.",
  profileMfaTotpDisabled: "Authenticator app MFA is not enabled.",
  profileMfaEmailFallback: "Email OTP remains available as a fallback.",
  profileMfaStartTotp: "Set up authenticator app",
  profileMfaUpdateTotp: "Update authenticator app",
  profileMfaDisableTotp: "Disable authenticator app",
  profileMfaCurrentCode: "Current authenticator code",
  profileMfaDisableCodeRequired: "Enter a current authenticator code before disabling MFA.",
  profileMfaDisabled: "Authenticator app MFA is disabled.",
  profileMfaScanPrompt: "Scan the QR code or enter the setup key, then confirm with a current code.",
  profileMfaStartFailed: "Could not start authenticator setup.",
  profileMfaInvalidCode: "Invalid authenticator code.",
  profileMfaEnabled: "Authenticator app MFA is enabled.",
  profileMfaQrAlt: "Authenticator setup QR code",
  profileMfaManualKey: "Manual setup key",
  profileMfaConfirmCode: "Confirmation code",
  profileMfaConfirm: "Confirm authenticator",
  planFreeName: "Free",
  profileOptionalPending: "Coming soon",
  profileRequiredMissing: "Required field is missing",
  profileNotAvailable: "Not available"
};

vi.mock("../components/LanguageProvider", () => ({
  useLanguage: () => ({
    t: (key: string) => labels[key] ?? key
  })
}));

describe("Profile page", () => {
  beforeEach(() => {
    authMocks.updateProfile.mockReset();
    authMocks.sendEmailChangeCode.mockReset();
    authMocks.completeEmailChange.mockReset();
    authMocks.refreshUser.mockReset();
    authMocks.user.mfaTotpEnabled = false;
    authMocks.updateProfile.mockResolvedValue({});
    authMocks.sendEmailChangeCode.mockResolvedValue(undefined);
    authMocks.completeEmailChange.mockResolvedValue({});
    authMocks.refreshUser.mockResolvedValue({});
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    cleanup();
  });

  it("renders structured user info from API auth state", () => {
    render(
      <MemoryRouter>
        <Profile />
      </MemoryRouter>
    );

    expect(screen.getByText("My Profile")).toBeDefined();
    expect(
      screen.getByText("Profile data will be reused automatically when creating legal documents.")
    ).toBeDefined();
    expect(screen.getByText("User ID")).toBeDefined();
    expect(screen.getByText("user-1")).toBeDefined();
    expect(screen.getByText("First Name")).toBeDefined();
    expect(screen.getByDisplayValue("Admin")).toBeDefined();
    expect(screen.getByDisplayValue("Admin").hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "Edit" })).toBeDefined();
    expect(screen.queryByRole("button", { name: "Save changes" })).toBeNull();
    expect(screen.getByText("Last Name")).toBeDefined();
    expect(screen.getByDisplayValue("User")).toBeDefined();
    expect(screen.getByText("Full Name")).toBeDefined();
    expect(screen.getByText("Admin User")).toBeDefined();
    expect(screen.getByText("Email")).toBeDefined();
    expect(screen.getByDisplayValue("user@example.com")).toBeDefined();
    expect(screen.getByText("Phone number (required)")).toBeDefined();
    expect(screen.getByDisplayValue("+421900111222")).toBeDefined();
    expect(screen.getByText("Address")).toBeDefined();
    expect(screen.getByDisplayValue("Main Street 1")).toBeDefined();
    expect(screen.getByText("IČO / tax number")).toBeDefined();
    expect(screen.getByDisplayValue("12345678")).toBeDefined();
    expect(screen.getByText("Identity card number")).toBeDefined();
    expect(screen.getByDisplayValue("AB123456")).toBeDefined();
    expect(screen.getByText("Role")).toBeDefined();
    expect(screen.getByText("JurisDigta user")).toBeDefined();
    expect(screen.getByText("Account Created Date")).toBeDefined();
    expect(screen.getByText("Billing cadence")).toBeDefined();
    expect(screen.getByText("Opened cases")).toBeDefined();
    expect(screen.getByText("Keystone Holdings Intake")).toBeDefined();
    expect(screen.getByText("My Documents")).toBeDefined();
    expect(screen.getByText("keystone-timeline.pdf")).toBeDefined();
    expect(screen.getByText("Case: Keystone Holdings Intake")).toBeDefined();
  });

  it("saves editable profile fields", async () => {
    render(
      <MemoryRouter>
        <Profile />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Address"), { target: { value: "Updated Street 2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(authMocks.updateProfile).toHaveBeenCalledWith(
        expect.objectContaining({
          phoneNumber: "+421900111222",
          address: "Updated Street 2"
        })
      );
    });
    expect(authMocks.completeEmailChange).not.toHaveBeenCalled();
  });

  it("requires OTP before saving an email change", async () => {
    render(
      <MemoryRouter>
        <Profile />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(screen.getByRole("alert").textContent).toBe("Email change requires OTP code.");
    expect(authMocks.updateProfile).not.toHaveBeenCalled();
  });

  it("sends OTP and completes an email change", async () => {
    render(
      <MemoryRouter>
        <Profile />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Send OTP code" }));
    await waitFor(() => {
      expect(authMocks.sendEmailChangeCode).toHaveBeenCalledWith("new@example.com");
    });
    expect(screen.getByText("OTP code sent.")).toBeDefined();

    fireEvent.change(screen.getByLabelText("OTP code for email change"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(authMocks.completeEmailChange).toHaveBeenCalledWith("new@example.com", "123456");
    });
  });

  it("allows an enabled authenticator app to be updated", async () => {
    authMocks.user.mfaTotpEnabled = true;
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          manual_setup_key: "ABCDEF",
          qr_code_uri: "data:image/png;base64,abc"
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    );

    render(
      <MemoryRouter>
        <Profile />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole("button", { name: "Update authenticator app" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/v1/users/user-1/mfa/totp/start"),
        expect.objectContaining({ method: "POST" })
      );
    });
    expect(screen.getByDisplayValue("ABCDEF")).toBeDefined();
    expect(screen.getByLabelText("Confirmation code")).toBeDefined();
  });

  it("disables an enabled authenticator app with the current code", async () => {
    authMocks.user.mfaTotpEnabled = true;
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({}), { status: 200 }));

    render(
      <MemoryRouter>
        <Profile />
      </MemoryRouter>
    );

    fireEvent.change(screen.getByLabelText("Current authenticator code"), {
      target: { value: "123456" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Disable authenticator app" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/v1/users/user-1/mfa/totp"),
        expect.objectContaining({
          method: "DELETE",
          body: JSON.stringify({ verification_code: "123456" })
        })
      );
    });
    expect(authMocks.refreshUser).toHaveBeenCalledWith("user-1");
  });
});
