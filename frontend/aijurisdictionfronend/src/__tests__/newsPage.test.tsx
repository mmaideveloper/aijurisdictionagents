// @vitest-environment jsdom

import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import News from "../pages/News";

const labels: Record<string, string> = {
  newsEyebrow: "Product updates",
  navNews: "News",
  newsSubtitle: "Dated mini-blogs.",
  newsAudioModelsDate: "7 July 2026",
  newsMcpDate: "22 June 2026",
  newsLocalModelsDate: "7 July 2026",
  newsApprovalDate: "21 June 2026",
  newsMetadataDate: "20 June 2026",
  newsAudioModelsTitle: "STT/TTS improves communication between the client and the AI Lawyer",
  newsAudioModelsBody: "Audio models can record a client consultation.",
  newsLocalModelsTitle: "Local models for free users subscriptions with model routing.",
  newsLocalModelsBody: "Free users can be routed to local Ollama models.",
  newsMetadataBody: "Outputs keep visible metadata.",
  assistantMandatoryMcpTitle: "JurisDigta MCP",
  assistantMandatoryMcpBody: "JurisDigta API and MCP are always attached.",
  assistantMcpLocked: "Locked on",
  assistantToolsTitle: "Capabilities",
  assistantCapabilityLawSearch: "Law search and law text",
  assistantCapabilityOrsr: "ORSR company lookup",
  assistantCapabilityPerson: "Person verification",
  assistantCapabilityScreening: "Screening",
  assistantCapabilityCar: "Car verification",
  assistantCapabilityLocation: "Address verification",
  assistantApprovalTitle: "Human approval",
  assistantApprovalBody: "Sensitive tool calls require approval.",
  assistantMetadataTitle: "Transparency metadata"
};

vi.mock("../components/LanguageProvider", () => ({
  useLanguage: () => ({
    t: (key: string) => labels[key] ?? key
  })
}));

describe("News", () => {
  it("renders dated mini-blogs and removes old conversation buttons", () => {
    render(<News />);

    expect(screen.getByRole("heading", { name: "News" })).toBeDefined();
    expect(screen.getAllByText("7 July 2026")).toHaveLength(2);
    expect(
      screen.getByRole("heading", { name: "STT/TTS improves communication between the client and the AI Lawyer" })
    ).toBeDefined();
    expect(screen.getByText("Audio models can record a client consultation.")).toBeDefined();
    expect(
      screen.getByRole("heading", { name: "Local models for free users subscriptions with model routing." })
    ).toBeDefined();
    expect(screen.getByText("Free users can be routed to local Ollama models.")).toBeDefined();
    expect(screen.getByText("22 June 2026")).toBeDefined();
    expect(screen.getByRole("heading", { name: "JurisDigta MCP" })).toBeDefined();
    expect(screen.getByText("Locked on")).toBeDefined();
    expect(screen.getByRole("list")).toBeDefined();
    expect(screen.getByText("Law search and law text")).toBeDefined();
    expect(screen.getByText("20 June 2026")).toBeDefined();
    expect(screen.queryByRole("button", { name: "Current matter" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Document preparation" })).toBeNull();
  });
});
