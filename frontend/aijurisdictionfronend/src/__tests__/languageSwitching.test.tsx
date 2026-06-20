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
        <MemoryRouter initialEntries={["/home"]}>
          <PageLayout>
            <Routes>
              <Route path="/home" element={<Home />} />
              <Route path="/pricing" element={<Pricing />} />
            </Routes>
          </PageLayout>
        </MemoryRouter>
      </LanguageProvider>
    );

    expect(screen.getByText("What would you like to explore today?")).toBeDefined();

    await user.click(screen.getByRole("button", { name: "SK" }));

    expect(screen.getByText("Čo by ste dnes chceli preskúmať?")).toBeDefined();
    expect(window.localStorage.getItem("aj_frontend_lang")).toBe("sk");

    await user.click(screen.getByRole("link", { name: "Cenník" }));

    expect(screen.getByText("Zvoľte si tempo, ktoré vám vyhovuje.")).toBeDefined();
    expect(screen.getByRole("link", { name: "Domov" })).toBeDefined();
  });
});
