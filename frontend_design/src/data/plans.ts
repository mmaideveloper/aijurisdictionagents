import { TranslationKey } from "./translations";

export type BillingCadence = "monthly" | "yearly";

export interface Plan {
  id: "free" | "basic" | "pro" | "ultra";
  nameKey: TranslationKey;
  descriptionKey: TranslationKey;
  featureKeys: TranslationKey[];
  priceMonthly: number;
  priceYearly: number;
  highlight?: boolean;
}

export const plans: Plan[] = [
  {
    id: "free",
    nameKey: "planFreeName",
    descriptionKey: "planFreeDescription",
    featureKeys: ["planFreeFeature1", "planFreeFeature2", "planFreeFeature3"],
    priceMonthly: 0,
    priceYearly: 0
  },
  {
    id: "basic",
    nameKey: "planBasicName",
    descriptionKey: "planBasicDescription",
    featureKeys: ["planBasicFeature1", "planBasicFeature2", "planBasicFeature3"],
    priceMonthly: 39,
    priceYearly: 390
  },
  {
    id: "pro",
    nameKey: "planProName",
    descriptionKey: "planProDescription",
    featureKeys: ["planProFeature1", "planProFeature2", "planProFeature3"],
    priceMonthly: 89,
    priceYearly: 890,
    highlight: true
  },
  {
    id: "ultra",
    nameKey: "planUltraName",
    descriptionKey: "planUltraDescription",
    featureKeys: ["planUltraFeature1", "planUltraFeature2", "planUltraFeature3"],
    priceMonthly: 179,
    priceYearly: 1790
  }
];
