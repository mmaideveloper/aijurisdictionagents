import { TranslationKey } from "./translations";

export interface Plan {
  id: "free" | "case" | "basic" | "premium";
  nameKey: TranslationKey;
  descriptionKey: TranslationKey;
  featureKeys: TranslationKey[];
  priceLabelKey: TranslationKey;
  highlight?: boolean;
  disabled?: boolean;
}

export const plans: Plan[] = [
  {
    id: "free",
    nameKey: "planFreeName",
    descriptionKey: "planFreeDescription",
    featureKeys: ["planFreeFeature1", "planFreeFeature2", "planFreeFeature3"],
    priceLabelKey: "planFreePrice"
  },
  {
    id: "case",
    nameKey: "planProName",
    descriptionKey: "planProDescription",
    featureKeys: ["planProFeature1", "planProFeature2", "planProFeature3"],
    priceLabelKey: "planProPrice",
    highlight: true,
    disabled: true
  },
  {
    id: "basic",
    nameKey: "planBasicName",
    descriptionKey: "planBasicDescription",
    featureKeys: ["planBasicFeature1", "planBasicFeature2", "planBasicFeature3"],
    priceLabelKey: "pricingComingSoon",
    disabled: true
  },
  {
    id: "premium",
    nameKey: "planUltraName",
    descriptionKey: "planUltraDescription",
    featureKeys: ["planUltraFeature1", "planUltraFeature2", "planUltraFeature3"],
    priceLabelKey: "pricingComingSoon",
    disabled: true
  }
];
