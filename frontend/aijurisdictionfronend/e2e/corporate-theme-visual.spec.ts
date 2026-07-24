import { expect, test } from "@playwright/test";

const corporateTheme = {
  ink: "#082046",
  primary: "#06397a",
  primaryRgb: "rgb(6, 57, 122)"
} as const;

test("authentication page uses the corporate JurisDigta theme", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(() => {
    window.localStorage.setItem("aj_frontend_lang", "en");
  });
  await page.goto("/auth", { waitUntil: "domcontentloaded" });
  await page.evaluate(() => document.fonts.ready);

  const heading = page.getByRole("heading", { name: "Secure access" });
  const primaryButton = page.getByRole("button", { name: "Sign in" });
  const brandShield = page.locator(".nav-brand .brand-mark");
  await expect(heading).toBeVisible();
  await expect(primaryButton).toBeVisible();
  await expect(brandShield).toBeVisible();
  await expect(brandShield).toHaveAttribute("src", "/login-shield.png");

  await page.screenshot({
    path: "output/playwright/codex-576/01-auth-corporate-theme.png",
    fullPage: true
  });

  const renderedTheme = await page.evaluate(() => {
    const rootStyle = getComputedStyle(document.documentElement);
    const bodyStyle = getComputedStyle(document.body);
    const headingStyle = getComputedStyle(document.querySelector("h1")!);
    const primaryButtonStyle = getComputedStyle(document.querySelector(".button.primary")!);

    return {
      accent: rootStyle.getPropertyValue("--accent").trim().toLowerCase(),
      ink: rootStyle.getPropertyValue("--ink").trim().toLowerCase(),
      bodyFont: bodyStyle.fontFamily,
      headingFont: headingStyle.fontFamily,
      brandShieldWidth: getComputedStyle(document.querySelector(".nav-brand .brand-mark")!).width,
      primaryButtonBackground: primaryButtonStyle.backgroundColor
    };
  });

  expect.soft(renderedTheme.accent).toBe(corporateTheme.primary);
  expect.soft(renderedTheme.ink).toBe(corporateTheme.ink);
  expect.soft(renderedTheme.primaryButtonBackground).toBe(corporateTheme.primaryRgb);
  expect.soft(renderedTheme.brandShieldWidth).toBe("44px");
  expect.soft(renderedTheme.bodyFont).toContain("Source Serif 4");
  expect.soft(renderedTheme.headingFont).toContain("Space Grotesk");
});
