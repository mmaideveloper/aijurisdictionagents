import { expect, test } from "@playwright/test";

const languages = [
  {
    code: "sk",
    legalTitle: "Právne informácie",
    privacyTitle: "Zásady súkromia"
  },
  {
    code: "de",
    legalTitle: "Rechtliche Informationen",
    privacyTitle: "Datenschutz"
  },
  {
    code: "en",
    legalTitle: "Legal information",
    privacyTitle: "Privacy Policy"
  }
] as const;

test("legal section renders in Slovak, German, and English", async ({
  page
}, testInfo) => {
  await page.route("**/*.mp4", (route) => route.abort());
  await page.goto("/#privacy", { waitUntil: "domcontentloaded" });

  const legalSection = page.locator("section#legal");
  await expect(legalSection).toBeVisible();
  await expect(legalSection.locator(".legal-card")).toHaveCount(5);

  for (const language of languages) {
    await page.locator(`.lang-btn[data-lang="${language.code}"]`).click();

    await expect(page.locator("html")).toHaveAttribute("lang", language.code);
    await expect(legalSection.locator("h2")).toHaveText(language.legalTitle);
    await expect(legalSection.locator("#privacy h3")).toHaveText(
      language.privacyTitle
    );

    const screenshotPath = testInfo.outputPath(
      `corporate-legal-${language.code}.png`
    );
    await legalSection.screenshot({
      animations: "disabled",
      path: screenshotPath
    });
    await testInfo.attach(`corporate-legal-${language.code}`, {
      contentType: "image/png",
      path: screenshotPath
    });
  }
});
