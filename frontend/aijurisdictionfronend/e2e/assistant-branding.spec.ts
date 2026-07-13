import { expect, test } from "@playwright/test";

const productNames = {
  sk: "Jurisdigta AI právnik",
  en: "Jurisdigta AI lawyer",
  de: "Jurisdigta AI Anwalt"
} as const;

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
        userId: "issue-530-e2e-user",
        email: "issue-530@example.test",
        name: "Issue 530 Reviewer"
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
    await expect(page.locator(".sidebar-brand strong")).toHaveText(productName);
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
  await expect(page.locator(".sidebar-brand strong")).toHaveText(productNames.de);
  await page.screenshot({
    path: "../../runs/e2e/issue-530-assistant-branding.png",
    fullPage: true
  });
});
