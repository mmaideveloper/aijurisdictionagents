import { expect, test } from "@playwright/test";

const agentOrigin = "https://agent.jurisdigta.eu";
const labels = {
  sk: "Otvoriť JurisDigta Agent",
  de: "JurisDigta Agent öffnen",
  en: "Open JurisDigta Agent"
} as const;

test.describe("agent application entry point", () => {
  for (const [code, label] of Object.entries(labels)) {
    test(`shows the exact agent destination in ${code.toUpperCase()}`, async ({
      page
    }) => {
      await page.route("**/*.mp4", (route) => route.abort());
      await page.goto("/", { waitUntil: "domcontentloaded" });
      await page.locator(`.lang-btn[data-lang="${code}"]`).click();

      const productTitle = page.locator(".product-title");
      const agentLink = page.getByRole("link", { name: label, exact: true });

      await expect(productTitle).toBeVisible();
      await expect(agentLink).toBeVisible();
      await expect(agentLink).toHaveAttribute("href", agentOrigin);
      await expect(agentLink).not.toHaveAttribute("target", "_blank");
      expect(await agentLink.evaluate((link) => Boolean(
        link.compareDocumentPosition(document.querySelector(".product-title")!)
          & Node.DOCUMENT_POSITION_PRECEDING
      ))).toBe(true);
    });
  }

  test("navigates in the same tab and captures the mobile entry point", async ({
    page
  }, testInfo) => {
    await page.setViewportSize({ width: 689, height: 856 });
    await page.route("**/*.mp4", (route) => route.abort());
    await page.goto("/", { waitUntil: "domcontentloaded" });

    const agentLink = page.getByRole("link", {
      name: labels.sk,
      exact: true
    });
    await expect(agentLink).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath("issue-681-corporate-agent-entry-mobile.png")
    });

    await Promise.all([
      page.waitForURL(`${agentOrigin}/**`, { waitUntil: "domcontentloaded" }),
      agentLink.click()
    ]);

    await expect(page).toHaveURL(new RegExp(`^${agentOrigin.replaceAll(".", "\\.")}/`));
  });
});
