import { expect, test } from "@playwright/test";

const languageVersions = [
  {
    button: "SK",
    heading: "Podmienky služby",
    summary:
      "Tieto podmienky upravujú používanie služieb, rozhraní a výstupov platformy Jurisdigta AI právnik.",
    screenshot: "terms-sk.png"
  },
  {
    button: "EN",
    heading: "Terms of Service",
    summary:
      "These terms govern your use of AIJurisdiction services, interfaces, and generated outputs.",
    screenshot: "terms-en.png"
  },
  {
    button: "DE",
    heading: "Nutzungsbedingungen",
    summary:
      "Diese Bedingungen regeln die Nutzung von AIJurisdiction, einschliesslich Oberflachen und erzeugter Inhalte.",
    screenshot: "terms-de.png"
  }
] as const;

test("terms page renders and captures all three language versions", async ({ page }) => {
  await page.goto("/terms", { waitUntil: "domcontentloaded" });

  const termsArticle = page.locator("article.legal-shell");

  for (const language of languageVersions) {
    const languageButton = page.getByRole("button", {
      name: language.button,
      exact: true
    });

    await languageButton.click();

    await expect(languageButton).toHaveAttribute("aria-pressed", "true");
    await expect(termsArticle.getByRole("heading", { level: 1 })).toHaveText(language.heading);
    await expect(termsArticle).toContainText(language.summary);

    if (language.button === "SK") {
      await expect(
        termsArticle.getByRole("link", { name: "Ochrana súkromia", exact: true })
      ).toHaveAttribute("href", "/privacy");
    }

    await page.screenshot({
      path: `../../runs/e2e/${language.screenshot}`,
      fullPage: true
    });
  }
});
