// @vitest-environment jsdom

import React from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { LanguageProvider } from "../components/LanguageProvider";
import TermsOfService from "../pages/TermsOfService";

describe("Slovak terms page", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders corrected branding, privacy guidance, and AI oversight wording", () => {
    render(
      <LanguageProvider>
        <MemoryRouter>
          <TermsOfService />
        </MemoryRouter>
      </LanguageProvider>
    );

    expect(screen.getByRole("heading", { name: "Podmienky služby" })).toBeDefined();
    expect(
      screen.getByText(
        "Tieto podmienky upravujú používanie služieb, rozhraní a výstupov platformy Jurisdigta AI právnik."
      )
    ).toBeDefined();
    expect(screen.getByRole("heading", { name: "Povolené použitie" })).toBeDefined();
    expect(screen.getByText(/iba zákonným spôsobom/)).toBeDefined();
    expect(screen.getByRole("heading", { name: "Ochrana osobných údajov" })).toBeDefined();
    expect(screen.getByRole("link", { name: "Ochrana súkromia" }).getAttribute("href")).toBe("/privacy");
    expect(
      screen.getByRole("heading", { name: "Výstupy umelej inteligencie a ľudský dohľad" })
    ).toBeDefined();
    expect(screen.getByText(/zabezpečte primerané ľudské posúdenie/)).toBeDefined();
    expect(document.body.textContent).not.toContain("AIJurisdiction");
    expect(screen.getByText("15. júla 2026")).toBeDefined();
  });
});
