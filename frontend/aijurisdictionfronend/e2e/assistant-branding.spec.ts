import { expect, test } from "@playwright/test";

const productNames = {
  sk: "JurisDigta AI právnik",
  en: "JurisDigta AI lawyer",
  de: "JurisDigta AI Anwalt"
} as const;

test.use({ viewport: { width: 1440, height: 900 } });

test.beforeEach(async ({ page }) => {
  await page.route("**/v1/model-routing/effective?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        plan_code: "free",
        route_type: "free_local",
        provider: "local_ollama",
        provider_display_name: "Local Ollama",
        model: "qwen3:1.7b",
        model_profile_id: "local_ollama_default",
        is_local: true,
        is_external: false,
        label: "Local Ollama - qwen3:1.7b"
      })
    });
  });

  await page.route("**/v1/cases?user_id=**", async (route) => {
    await route.fulfill({ contentType: "application/json", body: "[]" });
  });

  await page.addInitScript(() => {
    window.sessionStorage.setItem(
      "jurisdigta.web.auth.user.v1",
      JSON.stringify({
        userId: "issue-574-e2e-user",
        email: "issue-574@example.test",
        name: "Issue 574 Reviewer"
      })
    );
  });
});

for (const [language, productName] of Object.entries(productNames)) {
  test(`shows the ${language.toUpperCase()} assistant brand on direct load`, async ({ page }) => {
    await page.addInitScript((persistedLanguage) => {
      window.localStorage.setItem("aj_frontend_lang", persistedLanguage);
    }, language);

    await page.goto("/app/assistant", { waitUntil: "domcontentloaded" });

    await expect(page).toHaveTitle(productName);
    await expect(page.locator(".nav-brand strong")).toHaveText(productName);
    await expect(page.locator(".sidebar-brand strong")).toHaveText(productName);
    await page.screenshot({
      path: `../../runs/e2e/issue-574-assistant-branding-${language}.png`,
      animations: "disabled"
    });
  });
}

test("updates the assistant brand when language changes and after navigation", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("aj_frontend_lang", "sk");
  });
  await page.goto("/app/assistant", { waitUntil: "domcontentloaded" });

  for (const [language, productName] of Object.entries(productNames)) {
    await page.getByRole("button", { name: language.toUpperCase(), exact: true }).click();
    await expect(page).toHaveTitle(productName);
    await expect(page.locator(".nav-brand strong")).toHaveText(productName);
    await expect(page.locator(".sidebar-brand strong")).toHaveText(productName);
  }

  await page.locator("button.sidebar-action").click();
  await expect(page).toHaveURL(/\/app\/case$/);
  await page.evaluate(() => {
    document.title = "AIJurisdiction Front";
  });
  await page.goBack();

  await expect(page).toHaveURL(/\/app\/assistant$/);
  await expect(page).toHaveTitle(productNames.de);
  await expect(page.locator(".nav-brand strong")).toHaveText(productNames.de);
  await expect(page.locator(".sidebar-brand strong")).toHaveText(productNames.de);
  await page.screenshot({
    path: "../../runs/e2e/issue-574-assistant-branding.png",
    fullPage: true
  });
});
