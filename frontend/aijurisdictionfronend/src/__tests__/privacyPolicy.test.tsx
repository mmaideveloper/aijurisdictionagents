// @vitest-environment jsdom

import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { LanguageProvider } from "../components/LanguageProvider";
import { legalContent } from "../content/legal";
import PrivacyPolicy from "../pages/PrivacyPolicy";

const renderPrivacyPolicy = (language: "sk" | "en" | "de") => {
  window.localStorage.setItem("aj_frontend_lang", language);
  return render(
    <LanguageProvider>
      <PrivacyPolicy />
    </LanguageProvider>
  );
};

describe("privacy policy", () => {
  afterEach(() => {
    cleanup();
    window.localStorage.clear();
  });

  it("renders the corrected Slovak privacy copy and contact routes", () => {
    renderPrivacyPolicy("sk");

    expect(screen.getByRole("heading", { level: 1, name: "Ochrana súkromia" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Aké údaje zbierame" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Aké údaje používame" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Zdieľanie údajov" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Uchovávanie a bezpečnosť" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Vaše práva" })).toBeDefined();
    expect(screen.getByText(/Posledná aktualizácia:/)).toBeDefined();
    expect(screen.getByRole("link", { name: "Napísať kontaktu pre ochranu súkromia" })).toHaveProperty(
      "href",
      "mailto:info@jurisdigta.eu"
    );
    expect(screen.getByRole("link", { name: "Úrad na ochranu osobných údajov SR" })).toHaveProperty(
      "href",
      "https://dataprotection.gov.sk/sk/kontakt/"
    );
  });

  it("keeps controller, model-routing, retention, and human-oversight disclosures in every language", () => {
    for (const language of ["sk", "en", "de"] as const) {
      const privacy = legalContent[language].privacy;
      const text = [privacy.summary, ...privacy.sections.map((section) => section.body)].join(" ");

      expect(text).toContain("Esolutions SK s.r.o.");
      expect(text).toContain("46491261");
      expect(text).toContain("info@jurisdigta.eu");
      expect(text).toContain("Ollama");
      expect(text).toContain("Azure AI Foundry");
      expect(text).toContain("431/2002");
    }
  });

  it("does not regress to the old Slovak labels or product name", () => {
    const privacy = legalContent.sk.privacy;
    const text = [
      legalContent.sk.footerLinks.privacy,
      privacy.title,
      privacy.summary,
      privacy.lastUpdatedLabel,
      ...privacy.sections.flatMap((section) => [section.heading, section.body])
    ].join(" ");

    expect(text).not.toContain("AIJurisdiction");
    expect(text).not.toContain("Ochrana sukromia");
    expect(text).not.toContain("Ake udaje");
    expect(text).not.toContain("Zdielanie udajov");
    expect(text).not.toContain("Vase prava");
    expect(text).not.toContain("Posledna aktualizacia");
  });
});
