import { describe, expect, it } from "vitest";
import { PRODUCT_NAMES } from "../branding";
import { legalContent } from "../content/legal";
import type { Language } from "../data/translations";

const languages: Language[] = ["en", "sk", "de"];

describe("multilingual disclaimer content", () => {
  it.each(languages)("uses the current product title in %s", (language) => {
    const disclaimer = legalContent[language].disclaimer;
    const renderedText = JSON.stringify(disclaimer);

    expect(renderedText).toContain(PRODUCT_NAMES[language]);
    expect(renderedText).not.toContain("AIJurisdiction");
  });

  it.each(languages)(
    "includes AI transparency, human review, and privacy safeguards in %s",
    (language) => {
      const disclaimer = legalContent[language].disclaimer;

      expect(disclaimer.sections).toHaveLength(11);
      expect(disclaimer.sections.at(0)?.body).toMatch(
        /AI|KI|umelej inteligencie/
      );
      expect(disclaimer.sections.at(2)?.body).toMatch(
        /qualified legal professional|kvalifikovaným právnikom|qualifizierten juristischen Fachkraft/
      );
      expect(disclaimer.sections.at(8)?.body).toMatch(
        /special-category personal data|osobitné kategórie osobných údajov|besonderen Kategorien personenbezogener Daten/
      );
    }
  );

  it("keeps Slovak and German diacritics in user-visible text", () => {
    expect(legalContent.sk.disclaimer.lastUpdatedLabel).toBe(
      "Posledná aktualizácia"
    );
    expect(legalContent.sk.disclaimer.sections.at(0)?.heading).toBe(
      "Informácie generované umelou inteligenciou"
    );
    expect(legalContent.de.disclaimer.sections.at(3)?.heading).toBe(
      "Kein Mandatsverhältnis"
    );
    expect(legalContent.de.disclaimer.sections.at(5)?.heading).toBe(
      "Keine Gewährleistung"
    );
  });
});
