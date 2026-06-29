import { describe, expect, it } from "vitest";
import { apiProfileToAuthUser } from "../auth/webAuth";

describe("web auth profile mapping", () => {
  it("maps API user profile fields into frontend auth state", () => {
    expect(
      apiProfileToAuthUser({
        user_id: "user-1",
        phone_number: "+421900111222",
        email: "founder@example.com",
        first_name: "Marek",
        last_name: "Founder",
        full_name: "Marek Founder",
        address: "Partizanska 665",
        city: "Spisske Bystre",
        country: "SK",
        zip_code: "059 18",
        tax_number: "1070000001",
        identity_card_number: "AB123456",
        date_of_birth: "1980-01-02",
        social_security_number: "800102/1234",
        data_processing_consent_at: "2026-06-21T09:12:28+00:00",
        data_processing_consent_version: "web-sign-up-v1",
        mcp_api_key_expires_at: "2026-06-22T09:12:28+00:00",
        created_at: "2026-06-21T09:12:28+00:00",
        role: "admin",
        is_enabled: true
      })
    ).toEqual({
      userId: "user-1",
      phoneNumber: "+421900111222",
      email: "founder@example.com",
      firstName: "Marek",
      lastName: "Founder",
      name: "Marek Founder",
      address: "Partizanska 665",
      city: "Spisske Bystre",
      country: "SK",
      zipCode: "059 18",
      taxNumber: "1070000001",
      identityCardNumber: "AB123456",
      dateOfBirth: "1980-01-02",
      socialSecurityNumber: "800102/1234",
      dataProcessingConsentAt: "2026-06-21T09:12:28+00:00",
      dataProcessingConsentVersion: "web-sign-up-v1",
      mcpApiKeyExpiresAt: "2026-06-22T09:12:28+00:00",
      accountCreatedAt: "2026-06-21T09:12:28+00:00",
      role: "admin",
      isEnabled: true
    });
  });

  it("falls back to email when the API profile has no display name", () => {
    expect(
      apiProfileToAuthUser({
        user_id: "user-2",
        phone_number: null,
        email: "fallback@example.com",
        first_name: null,
        last_name: null,
        full_name: ""
      }).name
    ).toBe("fallback@example.com");
  });
});
