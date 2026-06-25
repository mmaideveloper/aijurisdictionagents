// @vitest-environment jsdom

import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { LanguageProvider } from "../components/LanguageProvider";
import Home from "../pages/Home";

const mockCaseState = vi.hoisted(() => ({
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
}));

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
      interactionHistory: mockCaseState.interactionHistory
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
  beforeEach(() => {
    mockCaseState.interactionHistory = [
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
    ];
    Element.prototype.scrollIntoView = vi.fn();
  });

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

  it("scrolls to the end of the newest non-user chat response", () => {
    mockCaseState.interactionHistory = [
      ...mockCaseState.interactionHistory,
      {
        id: "interaction-3",
        actor: "AI Lawyer",
        message: "I reviewed the uploaded documents.",
        createdAt: "2026-04-16T10:03:00.000Z"
      }
    ];

    render(
      <LanguageProvider>
        <MemoryRouter initialEntries={["/"]}>
          <Home />
        </MemoryRouter>
      </LanguageProvider>
    );

    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith({
      block: "end",
      behavior: "smooth"
    });
  });
});
