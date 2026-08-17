import { expect, test } from "@playwright/test";
import fs from "node:fs";

type LiveE2EManifest = {
  synthetic_only: boolean;
  user: { userId: string; email: string; name: string };
  case_id: string;
  provider: string;
  model: string;
  model_profile_id: string;
  model_parameters: Record<string, boolean | number | string | null>;
};

const manifestPath = process.env.ISSUE_612_E2E_MANIFEST?.trim();
const screenshotPath = process.env.ISSUE_612_E2E_SCREENSHOT?.trim();
const hasLiveSetup = Boolean(manifestPath && screenshotPath && fs.existsSync(manifestPath));

test.skip(!hasLiveSetup, "Run scripts/run_issue_612_azure_foundry_e2e.ps1 to prepare live synthetic state.");
test.setTimeout(180_000);

test("streams Azure Foundry gpt-5-mini without unsupported inherited temperature", async ({ page }) => {
  const manifest = JSON.parse(fs.readFileSync(manifestPath!, "utf-8")) as LiveE2EManifest;
  expect(manifest.synthetic_only).toBe(true);
  expect(manifest.model_parameters).toEqual({ temperature: null });

  await page.addInitScript((user) => {
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
    window.localStorage.setItem("aj_frontend_lang", "sk");
  }, manifest.user);

  await page.goto("/app/assistant", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".case-item").filter({ hasText: "Issue 612 Azure Foundry v1 E2E" })).toBeVisible();
  await expect(page.locator(".assistant-model-disclosure")).toContainText(manifest.provider);
  await expect(page.locator(".assistant-model-disclosure")).toContainText(manifest.model);

  const prompt =
    "This is a synthetic connectivity test with no legal or personal data. " +
    "Reply with the exact marker ISSUE-612-AZURE-FOUNDRY-V1-OK and one short sentence.";
  await page.locator(".assistant-composer__input").fill(prompt);
  await page.locator(".assistant-composer__send").click();

  const thread = page.locator(".assistant-thread__viewport");
  await expect(thread).toContainText("ISSUE-612-AZURE-FOUNDRY-V1-OK", { timeout: 160_000 });
  await expect(thread).not.toContainText("api-version query parameter is not allowed");
  await expect(thread).not.toContainText("Unsupported value: 'temperature'");
  await expect(thread).not.toContainText("Asistent nemohol dokončiť požiadavku");

  await page.screenshot({ path: screenshotPath!, fullPage: true });
});
