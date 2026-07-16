export const PRODUCT_NAMES = {
  sk: "Jurisdigta AI právnik",
  en: "Jurisdigta AI lawyer",
  de: "Jurisdigta AI Anwalt"
} as const;

export type BrandLanguage = keyof typeof PRODUCT_NAMES;
