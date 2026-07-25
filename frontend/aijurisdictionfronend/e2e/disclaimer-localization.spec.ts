import { expect, test } from "@playwright/test";

const languageVersions = [
  {
    button: "SK",
    heading: "Upozornenie",
    productName: "JurisDigta AI právnik",
    humanReviewHeading: "Vyžaduje sa ľudská kontrola",
    privacyHeading: "Ochrana súkromia a minimalizácia údajov",
    privacyText: "osobitné kategórie osobných údajov",
    lastUpdated: "25. júla 2026",
    screenshot: "issue-583-disclaimer-sk.png"
  },
  {
    button: "EN",
    heading: "Disclaimer",
    productName: "JurisDigta AI lawyer",
    humanReviewHeading: "Human Review Required",
    privacyHeading: "Privacy and Data Minimization",
    privacyText: "special-category personal data",
    lastUpdated: "July 25, 2026",
    screenshot: "issue-583-disclaimer-en.png"
  },
  {
    button: "DE",
    heading: "Haftungsausschluss",
    productName: "JurisDigta AI Anwalt",
    humanReviewHeading: "Menschliche Prüfung erforderlich",
    privacyHeading: "Datenschutz und Datenminimierung",
    privacyText: "besonderen Kategorien personenbezogener Daten",
    lastUpdated: "25. Juli 2026",
    screenshot: "issue-583-disclaimer-de.png"
  }
] as const;

test("disclaimer renders compliant reviewed copy in all three languages", async ({
  page
}) => {
  await page.setViewportSize({ width: 1294, height: 912 });
  await page.goto("/disclaimer", { waitUntil: "domcontentloaded" });

  const disclaimerArticle = page.locator("article.legal-shell");

  for (const language of languageVersions) {
    const languageButton = page.getByRole("button", {
      name: language.button,
      exact: true
    });

    await languageButton.click();

    await expect(languageButton).toHaveAttribute("aria-pressed", "true");
    await expect(
      disclaimerArticle.getByRole("heading", {
        level: 1,
        name: language.heading
      })
    ).toBeVisible();
    await expect(disclaimerArticle).toContainText(language.productName);
    await expect(
      disclaimerArticle.getByRole("heading", {
        name: language.humanReviewHeading
      })
    ).toBeVisible();
    await expect(
      disclaimerArticle.getByRole("heading", {
        name: language.privacyHeading
      })
    ).toBeVisible();
    await expect(disclaimerArticle).toContainText(language.privacyText);
    await expect(disclaimerArticle).toContainText(language.lastUpdated);
    await expect(page.locator("body")).not.toContainText("AIJurisdiction");
    await expect(page.locator("footer.site-footer")).toContainText(
      `© 2026 ${language.productName}`
    );

    await page.screenshot({
      path: `../../runs/e2e/${language.screenshot}`,
      fullPage: true
    });
  }
});
