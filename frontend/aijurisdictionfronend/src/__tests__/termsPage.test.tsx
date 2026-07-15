// @vitest-environment jsdom

import React from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { LanguageProvider } from "../components/LanguageProvider";
import TermsOfService from "../pages/TermsOfService";

const languageVersions = [
  {
    language: "sk",
    heading: "Podmienky služby",
    summary:
      "Tieto podmienky upravujú používanie služieb, rozhraní a výstupov platformy Jurisdigta AI právnik.",
    privacyHeading: "Ochrana osobných údajov",
    privacyLink: "Ochrana súkromia",
    oversightHeading: "Výstupy umelej inteligencie a ľudský dohľad",
    lastUpdated: "15. júla 2026"
  },
  {
    language: "en",
    heading: "Terms of Service",
    summary:
      "These terms govern your use of Jurisdigta AI Lawyer services, interfaces, and generated outputs.",
    privacyHeading: "Personal Data Protection",
    privacyLink: "Privacy Policy",
    oversightHeading: "AI-Generated Outputs and Human Oversight",
    lastUpdated: "July 15, 2026"
  },
  {
    language: "de",
    heading: "Nutzungsbedingungen",
    summary:
      "Diese Bedingungen regeln die Nutzung der Dienste, Benutzeroberflächen und generierten Ausgaben von Jurisdigta AI Anwalt.",
    privacyHeading: "Schutz personenbezogener Daten",
    privacyLink: "Datenschutz",
    oversightHeading: "KI-Ausgaben und menschliche Aufsicht",
    lastUpdated: "15. Juli 2026"
  }
] as const;

describe("localized terms page", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it.each(languageVersions)(
    "renders corrected $language branding, privacy guidance, and AI oversight wording",
    ({ language, heading, summary, privacyHeading, privacyLink, oversightHeading, lastUpdated }) => {
      window.localStorage.setItem("aj_frontend_lang", language);

      render(
        <LanguageProvider>
          <MemoryRouter>
            <TermsOfService />
          </MemoryRouter>
        </LanguageProvider>
      );

      expect(screen.getByRole("heading", { name: heading })).toBeDefined();
      expect(screen.getByText(summary)).toBeDefined();
      expect(screen.getByRole("heading", { name: privacyHeading })).toBeDefined();
      expect(screen.getByRole("link", { name: privacyLink }).getAttribute("href")).toBe("/privacy");
      expect(screen.getByRole("heading", { name: oversightHeading })).toBeDefined();
      expect(document.body.textContent).not.toContain("AIJurisdiction");
      expect(screen.getByText(lastUpdated)).toBeDefined();
    }
  );
});
