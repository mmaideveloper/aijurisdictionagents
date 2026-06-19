// @vitest-environment jsdom

import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import AssistantWorkspace from "../pages/AssistantWorkspace";

const labels: Record<string, string> = {
  assistantThreadsTitle: "Conversations",
  assistantThreadCurrent: "Current matter",
  assistantThreadDocument: "Document preparation",
  assistantEyebrow: "Authenticated legal assistant",
  assistantTitle: "JurisDigta Assistant",
  assistantSubtitle: "Assistant subtitle",
  assistantApiAuthAccess: "Production access uses JurisDigta account login",
  assistantModesTitle: "Assistant modes",
  assistantModeLegalSearch: "Legal search",
  assistantModePrepareDocument: "Prepare document",
  assistantModeDraftDocument: "Draft document",
  assistantModeVerifyPerson: "Verify person",
  assistantModeVerifyCompany: "Verify company",
  assistantModeScreenPerson: "Screen person",
  assistantModeScreenCompany: "Screen company",
  assistantModeVerifyCar: "Verify car",
  assistantModeVerifyLocation: "Verify location",
  assistantToolsTitle: "Capabilities",
  assistantMandatoryMcpTitle: "JurisDigta MCP",
  assistantMandatoryMcpBody: "JurisDigta API and MCP are always attached.",
  assistantMcpLocked: "Locked on",
  assistantCapabilityLawSearch: "Law search and law text",
  assistantCapabilityOrsr: "ORSR company lookup placeholder",
  assistantCapabilityPerson: "Consent-gated person verification placeholder",
  assistantCapabilityScreening: "Person and company screening placeholder",
  assistantCapabilityCar: "Car validation placeholder",
  assistantCapabilityLocation: "Location validation placeholder",
  assistantApprovalTitle: "Human approval",
  assistantApprovalBody: "Sensitive tool calls require explicit approval.",
  assistantMetadataTitle: "Transparency metadata",
  assistantMetadataGenerated: "Generated output",
  assistantMetadataAiDraft: "AI-assisted draft",
  assistantMetadataRisk: "Risk level",
  assistantMetadataRiskValue: "Legal review required",
  assistantMetadataReview: "Human oversight",
  assistantMetadataReviewValue: "Required before final use",
  assistantComposerLabel: "Assistant message",
  assistantComposerPlaceholder: "Ask for legal research or document preparation...",
  assistantSend: "Send message",
  assistantRole: "Assistant",
  assistantUserRole: "You"
};

vi.mock("../components/LanguageProvider", () => ({
  useLanguage: () => ({
    t: (key: string) => labels[key] ?? key
  })
}));

vi.mock("@assistant-ui/react", () => ({
  AssistantRuntimeProvider: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ComposerPrimitive: {
    Root: ({ children, className }: { children: React.ReactNode; className?: string }) => (
      <form className={className}>{children}</form>
    ),
    Input: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...props} />,
    Send: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
      <button type="button" {...props}>
        {children}
      </button>
    )
  },
  MessagePrimitive: {
    Root: ({ children, className }: { children: React.ReactNode; className?: string }) => (
      <article className={className}>{children}</article>
    ),
    If: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    Parts: () => <p>JurisDigta Assistant is ready with JurisDigta API and MCP locked on.</p>
  },
  ThreadPrimitive: {
    Root: ({ children, className }: { children: React.ReactNode; className?: string }) => (
      <section className={className}>{children}</section>
    ),
    Viewport: ({ children, className }: { children: React.ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
    Messages: ({ components }: { components: { Message: React.FC } }) => {
      const Message = components.Message;
      return <Message />;
    }
  },
  useLocalRuntime: () => ({})
}));

describe("AssistantWorkspace", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders the locked JurisDigta MCP and compliance guardrails", () => {
    render(<AssistantWorkspace />);

    expect(screen.getByRole("heading", { name: "JurisDigta Assistant" })).toBeDefined();
    expect(screen.getByText("Locked on")).toBeDefined();
    expect(screen.getByText("Human approval")).toBeDefined();
    expect(screen.getByText("AI-assisted draft")).toBeDefined();
    expect(screen.getByText("Production access uses JurisDigta account login")).toBeDefined();
  });

  it("shows V1 assistant modes without arbitrary MCP URL entry", () => {
    render(<AssistantWorkspace />);

    expect(screen.getByRole("button", { name: "Legal search" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Verify company" })).toBeDefined();
    expect(screen.queryByLabelText(/mcp url/i)).toBeNull();
  });
});
