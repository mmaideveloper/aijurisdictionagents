import { describe, expect, it } from "vitest";
import { isValidCredentials, MOCK_USER } from "../auth/mockAuth";

describe("mock auth credentials", () => {
  it("accepts the configured admin credentials", () => {
    expect(isValidCredentials(MOCK_USER.email, MOCK_USER.password)).toBe(true);
  });

  it("rejects invalid credentials", () => {
    expect(isValidCredentials("user@example.com", "badpass")).toBe(false);
  });
});
