import { expect, test } from "@playwright/test";

const languageVersions = [
  {
    button: "SK",
    heading: "Podmienky služby",
    summary:
      "Tieto podmienky upravujú používanie služieb, rozhraní a výstupov platformy Jurisdigta AI právnik.",
    privacyLink: "Ochrana súkromia",
    screenshot: "terms-sk.png"
  },
  {
    button: "EN",
    heading: "Terms of Service",
    summary:
      "These terms govern your use of Jurisdigta AI Lawyer services, interfaces, and generated outputs.",
    privacyLink: "Privacy Policy",
    screenshot: "terms-en.png"
  },
  {
    button: "DE",
    heading: "Nutzungsbedingungen",
    summary:
      "Diese Bedingungen regeln die Nutzung der Dienste, Benutzeroberflächen und generierten Ausgaben von Jurisdigta AI Anwalt.",
    privacyLink: "Datenschutz",
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

    await expect(
      termsArticle.getByRole("link", { name: language.privacyLink, exact: true })
    ).toHaveAttribute("href", "/privacy");
    await expect(termsArticle).not.toContainText("AIJurisdiction");

    await page.screenshot({
      path: `../../runs/e2e/${language.screenshot}`,
      fullPage: true
    });
  }
});
