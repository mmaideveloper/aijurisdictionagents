export const PRODUCT_NAMES = {
  sk: "JurisDigta AI právnik",
  en: "JurisDigta AI lawyer",
  de: "JurisDigta AI Anwalt"
} as const;

export type BrandLanguage = keyof typeof PRODUCT_NAMES;
