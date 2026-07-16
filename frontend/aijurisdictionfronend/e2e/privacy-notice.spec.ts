import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("aj_frontend_lang", "sk");
  });
});

test("privacy notice exposes compliant localized content and contact routes", async ({ page }) => {
  await page.goto("/privacy", { waitUntil: "domcontentloaded" });

  await expect(page.getByRole("heading", { level: 1, name: "Ochrana súkromia" })).toBeVisible();
  await expect(page.getByText(/Esolutions SK s\.r\.o\., IČO 46491261/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Aké údaje zbierame" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Aké údaje používame" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Zdieľanie údajov" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Uchovávanie a bezpečnosť" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Vaše práva" })).toBeVisible();
  await expect(page.getByText(/lokálne modely Ollama/)).toBeVisible();
  await expect(page.getByText(/Microsoft Azure AI Foundry/)).toBeVisible();
  await expect(page.getByText(/nevykonáva schválenia ani právne rozhodnutia/)).toBeVisible();

  await expect(page.getByRole("link", { name: "Napísať kontaktu pre ochranu súkromia" })).toHaveAttribute(
    "href",
    "mailto:info@jurisdigta.eu"
  );
  await expect(page.getByRole("link", { name: "Úrad na ochranu osobných údajov SR" })).toHaveAttribute(
    "href",
    "https://dataprotection.gov.sk/sk/kontakt/"
  );
  await expect(page.locator("main")).not.toContainText("Ochrana sukromia");
  await expect(page.locator("main")).not.toContainText("AIJurisdiction");
  await page.screenshot({
    path: "../../runs/e2e/privacy-notice-sk.png",
    fullPage: true
  });

  await page.getByRole("button", { name: "EN" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Privacy Notice" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Automated decisions and human oversight" })).toBeVisible();
  await page.screenshot({
    path: "../../runs/e2e/privacy-notice-en.png",
    fullPage: true
  });

  await page.getByRole("button", { name: "DE" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Datenschutzhinweise" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Automatisierte Entscheidungen und menschliche Aufsicht" })
  ).toBeVisible();
  await page.screenshot({
    path: "../../runs/e2e/privacy-notice-de.png",
    fullPage: true
  });
});
