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
        full_name: "Marek Founder"
      })
    ).toEqual({
      userId: "user-1",
      phoneNumber: "+421900111222",
      email: "founder@example.com",
      firstName: "Marek",
      lastName: "Founder",
      name: "Marek Founder",
      role: "JurisDigta user"
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
