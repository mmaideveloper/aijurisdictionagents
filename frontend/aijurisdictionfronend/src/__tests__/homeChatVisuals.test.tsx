// @vitest-environment jsdom

import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { LanguageProvider } from "../components/LanguageProvider";
import Home from "../pages/Home";

vi.mock("../auth/webAuth", () => ({
  useAuth: () => ({
    isAuthenticated: true,
    user: {
      name: "Admin User",
      email: "user@example.com"
    },
    signOut: vi.fn()
  })
}));

vi.mock("../state/CaseProvider", () => ({
  buildLocalizedInteractionMessage: vi.fn(),
  useCases: () => ({
    cases: [
      {
        id: "case-001",
        title: "Keystone Holdings Intake",
        description: "EU + UK matter involving Northshore Advisory.",
        status: "In progress"
      }
    ],
    activeCase: {
      id: "case-001",
      title: "Keystone Holdings Intake",
      description: "EU + UK matter involving Northshore Advisory.",
      status: "In progress",
      selectedCommunicationMode: "Chat",
      selectedRole: "AI Lawyer",
      workspace: {
        meta: "Due in 2 days",
        nextAction: "Schedule a follow-up.",
        objective: "Prepare the briefing memo.",
        jurisdiction: "EU + UK",
        output: "Briefing memo + checklist"
      },
      interactionHistory: [
        {
          id: "interaction-1",
          actor: "System",
          message: "Stored 1 uploaded document in mock profile storage.",
          createdAt: "2026-04-16T10:00:00.000Z"
        },
        {
          id: "interaction-2",
          actor: "You",
          message: "Please review the jurisdiction scope.",
          createdAt: "2026-04-16T10:02:00.000Z"
        }
      ]
    },
    hasSelectedCase: true,
    continueRequested: false,
    setContinueRequested: vi.fn(),
    addInteraction: vi.fn(),
    sendCaseMessage: vi.fn(),
    setCaseRole: vi.fn(),
    setCaseCommunicationMode: vi.fn()
  })
}));

describe("Home chat visuals", () => {
  it("does not render the next recommended action field in the workspace chat", () => {
    render(
      <LanguageProvider>
        <MemoryRouter initialEntries={["/"]}>
          <Home />
        </MemoryRouter>
      </LanguageProvider>
    );

    expect(screen.queryByText("Next recommended action")).toBeNull();
    expect(screen.getByText("Keystone Holdings Intake")).toBeDefined();
    expect(screen.getByText("Pripojené cez API chat.")).toBeDefined();
  });
});
