// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { PrivacyControls } from "../components/PrivacyControls";
import { AITransparencyNotice } from "../components/AITransparencyNotice";

vi.mock("../auth/webAuth", () => ({ useAuth: () => ({ user: { userId: "synthetic-user", deviceId: "test-device", deviceAuthToken: "synthetic-token" } }) }));
vi.mock("../components/LanguageProvider", () => ({ useLanguage: () => ({ language: "en" }) }));
vi.mock("../api/chatClient", () => ({ chatApiRuntimeConfig: () => ({ baseUrl: "http://localhost:8389", apiKey: "synthetic-api" }) }));

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

test("records an explicit versioned consent decision using device authentication", async () => {
  const state = { notice_version: "389-v1", restricted: false, consents: { external_models: false, external_checks: false, marketing: false, sensitive_processing: false }, requests: [] };
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => state });
  vi.stubGlobal("fetch", fetcher);
  render(<PrivacyControls />);
  const consent = await screen.findByRole("checkbox", { name: /external AI provider/ });
  expect((consent as HTMLInputElement).checked).toBe(false);
  fireEvent.click(consent);
  await waitFor(() => expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/consents"), expect.objectContaining({
    method: "POST", body: JSON.stringify({ scope: "external_models", text_version: "389-v1", granted: true }),
    headers: expect.objectContaining({ "x-jurisdigta-device-token": "synthetic-token" })
  })));
  expect(screen.getByText(/Approval does not mean erasure is complete/)).toBeTruthy();
});

test("failed consent updates are not presented as accepted", async () => {
  const fetcher = vi.fn().mockRejectedValue(new Error("offline"));
  vi.stubGlobal("fetch", fetcher);
  render(<PrivacyControls />);
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(screen.queryByRole("checkbox")).toBeNull();
});

test("AI disclosure names recorded provider and model and requires human review", () => {
  render(<AITransparencyNotice metadata={{ model_provider: "azure_foundry", model_name: "gpt-4o-mini" }} />);
  expect(screen.getByText(/AI-generated draft/)).toBeTruthy();
  expect(screen.getByText(/human legal review/)).toBeTruthy();
  expect(screen.getByText(/azure_foundry \/ gpt-4o-mini/)).toBeTruthy();
});

test("an incompatible privacy response shows an error without granting controls", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ secret: "not-a-privacy-response" }) }));
  render(<PrivacyControls />);
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(screen.queryByRole("checkbox")).toBeNull();
});
