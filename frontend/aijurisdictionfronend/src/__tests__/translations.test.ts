import { describe, expect, it } from "vitest";
import { translations } from "../data/translations";
import { PRODUCT_NAME } from "../branding";

describe("translations", () => {
  it("has matching keys across languages", () => {
    const baseKeys = Object.keys(translations.en).sort();
    (Object.keys(translations) as Array<keyof typeof translations>).forEach((lang) => {
      const keys = Object.keys(translations[lang]).sort();
      expect(keys).toEqual(baseKeys);
    });
  });

  it("uses the Jurisdigta AI lawyer product name in every language", () => {
    (Object.keys(translations) as Array<keyof typeof translations>).forEach((lang) => {
      expect(translations[lang].appName).toBe(PRODUCT_NAME);
    });
  });
});
