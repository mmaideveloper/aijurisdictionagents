import { expect, test } from "@playwright/test";

const supportedLanguages = [
  { code: "sk", expectedAlt: "Logo JurisDigtaAgents" },
  { code: "de", expectedAlt: "Logo von JurisDigtaAgents" },
  { code: "en", expectedAlt: "JurisDigtaAgents logo" }
] as const;

test.describe("footer branding", () => {
  for (const { code, expectedAlt } of supportedLanguages) {
    test(`uses the JurisDigtaAgents title in ${code.toUpperCase()}`, async ({
      page
    }, testInfo) => {
      test.fail(
        testInfo.project.name === "reproduction",
        "Known failure until GitHub issue #580 updates the footer lockup and localized alternative text."
      );

      await page.route("**/*.mp4", (route) => route.abort());
      await page.goto("/", { waitUntil: "domcontentloaded" });
      await page.locator(`.lang-btn[data-lang="${code}"]`).click();

      const footer = page.locator("footer.footer");
      const lockup = footer.locator("img.footer-lockup");

      await footer.scrollIntoViewIfNeeded();
      await expect(lockup).toBeVisible();
      await expect
        .poll(() => lockup.evaluate((image) => image.complete))
        .toBe(true);

      await footer.screenshot({
        path: testInfo.outputPath(`${code}-footer-branding.png`)
      });

      await expect(lockup).toHaveAttribute("alt", expectedAlt, {
        timeout: 1_500
      });
    });
  }
});
