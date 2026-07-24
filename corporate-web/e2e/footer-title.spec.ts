import { expect, test } from "@playwright/test";

const supportedLanguages = [
  "sk",
  "de",
  "en"
] as const;

test.describe("footer branding", () => {
  for (const code of supportedLanguages) {
    test(`uses the JurisDigtaAgents title in ${code.toUpperCase()}`, async ({
      page
    }, testInfo) => {
      await page.route("**/*.mp4", (route) => route.abort());
      await page.goto("/", { waitUntil: "domcontentloaded" });
      await page.locator(`.lang-btn[data-lang="${code}"]`).click();

      const footer = page.locator("footer.footer");
      const lockup = footer.locator(".footer-lockup");
      const shield = lockup.locator("img.footer-lockup-shield");
      const title = lockup.locator(".footer-lockup-title");

      await footer.scrollIntoViewIfNeeded();
      await expect(lockup).toBeVisible();
      await expect(lockup).toHaveAttribute("aria-label", "JurisDigtaAgents");
      await expect(title).toHaveText("JurisDigtaAgents");
      await expect(shield).toBeVisible();
      await expect
        .poll(() => shield.evaluate((image) => image.complete))
        .toBe(true);

      await footer.screenshot({
        path: testInfo.outputPath(`${code}-footer-branding.png`)
      });
    });
  }
});
