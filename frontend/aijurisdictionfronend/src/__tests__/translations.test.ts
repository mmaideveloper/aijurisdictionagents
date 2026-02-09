import { describe, expect, it } from "vitest";
import { translations } from "../data/translations";

describe("translations", () => {
  it("has matching keys across languages", () => {
    const baseKeys = Object.keys(translations.en).sort();
    (Object.keys(translations) as Array<keyof typeof translations>).forEach((lang) => {
      const keys = Object.keys(translations[lang]).sort();
      expect(keys).toEqual(baseKeys);
    });
  });
});
