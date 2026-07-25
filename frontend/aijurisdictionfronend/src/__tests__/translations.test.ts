import { describe, expect, it } from "vitest";
import { translations } from "../data/translations";
import { PRODUCT_NAMES } from "../branding";

describe("translations", () => {
  it("has matching keys across languages", () => {
    const baseKeys = Object.keys(translations.en).sort();
    (Object.keys(translations) as Array<keyof typeof translations>).forEach((lang) => {
      const keys = Object.keys(translations[lang]).sort();
      expect(keys).toEqual(baseKeys);
    });
  });

  it("uses the localized Jurisdigta product name in every language", () => {
    expect(translations.sk.appName).toBe(PRODUCT_NAMES.sk);
    expect(translations.en.appName).toBe(PRODUCT_NAMES.en);
    expect(translations.de.appName).toBe(PRODUCT_NAMES.de);
    expect(translations.sk.footerCopy).toContain(PRODUCT_NAMES.sk);
    expect(translations.en.footerCopy).toContain(PRODUCT_NAMES.en);
    expect(translations.de.footerCopy).toContain(PRODUCT_NAMES.de);
    expect(
      [
        translations.sk.footerCopy,
        translations.en.footerCopy,
        translations.de.footerCopy
      ].join(" ")
    ).not.toContain("AIJurisdiction");
  });
});
