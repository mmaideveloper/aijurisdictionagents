// @vitest-environment jsdom

import React from "react";
import { describe, expect, it, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { LanguageProvider } from "../components/LanguageProvider";
import { PageLayout } from "../components/PageLayout";
import Home from "../pages/Home";
import Pricing from "../pages/Pricing";

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
  useCases: () => ({
    cases: [
      {
        id: "case-seeded",
        title: "Mock Case",
        description: "Mock description",
        status: "In progress",
        workspace: {
          meta: "Mock meta",
          nextAction: "Mock next action"
        }
      }
    ],
    activeCase: null,
    hasSelectedCase: false,
    continueRequested: false,
    setContinueRequested: vi.fn(),
    addInteraction: vi.fn(),
    sendCaseMessage: vi.fn(),
    setCaseRole: vi.fn(),
    setCaseCommunicationMode: vi.fn(),
    documents: [],
    selectCase: vi.fn()
  })
}));

describe("language switching", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("updates the current page immediately and keeps the selection after route navigation", async () => {
    const user = userEvent.setup();

    render(
      <LanguageProvider>
        <MemoryRouter initialEntries={["/"]}>
          <PageLayout>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/pricing" element={<Pricing />} />
            </Routes>
          </PageLayout>
        </MemoryRouter>
      </LanguageProvider>
    );

    expect(screen.getByText("Čo by ste dnes chceli preskúmať?")).toBeDefined();
    expect(screen.getByText("Konfigurácie")).toBeDefined();

    await user.click(screen.getByRole("button", { name: "EN" }));

    expect(screen.getByText("What would you like to explore today?")).toBeDefined();
    expect(screen.getByText("Configurations")).toBeDefined();
    expect(window.localStorage.getItem("aj_frontend_lang")).toBe("en");

    await user.click(screen.getByRole("link", { name: "Pricing" }));

    expect(
      screen.getByText("Free is active now. A paid €10 Case plan is available; Basic and Premium are coming soon.")
    ).toBeDefined();
    expect(screen.getByText("Free access for one case, valid for 1 day.")).toBeDefined();
    expect(screen.getByText("Single paid case plan from the corporate pricing.")).toBeDefined();
    expect(screen.queryByRole("button", { name: "Monthly" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Yearly" })).toBeNull();
    expect(screen.getByText("Basic")).toBeDefined();
    expect(screen.getByText("Case")).toBeDefined();
    expect(screen.getByText("Premium")).toBeDefined();
    expect(screen.getByRole("button", { name: "Choose Free" }).hasAttribute("disabled")).toBe(false);
    expect(screen.getByRole("button", { name: "Choose Case" }).hasAttribute("disabled")).toBe(false);
    expect(screen.getAllByRole("button", { name: "Coming soon" })).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Home" })).toBeDefined();
  });
});
