import { expect, test } from '@playwright/test';

const frontendBaseUrl = process.env.FRONTEND_BASE_URL;
const authSessionKey = 'jurisdigta.web.auth.user.v1';

const desktopViewports = [
  { width: 1777, height: 794 },
  { width: 1638, height: 942 },
  { width: 1366, height: 768 },
  { width: 1280, height: 720 },
];

test.describe('frontend case creation assistant layout', () => {
  test.skip(!frontendBaseUrl, 'Set FRONTEND_BASE_URL to run frontend layout checks.');

  test.beforeEach(async ({ page }) => {
    await page.addInitScript((sessionKey) => {
      window.sessionStorage.setItem(
        sessionKey,
        JSON.stringify({
          userId: 'playwright-layout-user',
          email: 'playwright.layout@example.com',
          name: 'Playwright Layout',
          role: 'JurisDigta user',
        }),
      );
      window.localStorage.removeItem('aijurisdictionfrontend.mock.cases.v1');
    }, authSessionKey);
  });

  for (const viewport of desktopViewports) {
    test(`created case opens assistant without column overlap at ${viewport.width}x${viewport.height}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize(viewport);
      await page.goto(`${frontendBaseUrl}/app/case`);

      await page.getByLabel('Case name').fill(`Layout regression ${viewport.width}`);
      await page.getByLabel('Jurisdiction').fill('Slovakia');
      await page.getByLabel('Opposing party').fill('Northwind LLC');
      await page.getByRole('button', { name: 'Start AI lawyer chat' }).click();

      await expect(page).toHaveURL(/\/app\/assistant$/);
      await expect(page.locator('.assistant-workspace')).toBeVisible();

      const screenshotPath = testInfo.outputPath(
        `case-created-assistant-layout-${viewport.width}x${viewport.height}.png`,
      );
      await page.screenshot({ path: screenshotPath, fullPage: false });
      await testInfo.attach(`case-created-assistant-layout-${viewport.width}x${viewport.height}`, {
        path: screenshotPath,
        contentType: 'image/png',
      });

      const metrics = await page.evaluate(() => {
        const rectFor = (selector: string) => {
          const element = document.querySelector(selector);
          if (!element) {
            throw new Error(`Missing selector: ${selector}`);
          }
          const rect = element.getBoundingClientRect();
          return {
            left: rect.left,
            right: rect.right,
            width: rect.width,
          };
        };

        return {
          viewportWidth: window.innerWidth,
          scrollWidth: document.documentElement.scrollWidth,
          rail: rectFor('.assistant-rail'),
          main: rectFor('.assistant-main'),
          panel: rectFor('.assistant-tool-panel'),
        };
      });

      expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.viewportWidth + 1);
      expect(metrics.rail.right).toBeLessThanOrEqual(metrics.main.left);
      expect(metrics.main.right).toBeLessThanOrEqual(metrics.panel.left);
      expect(metrics.panel.right).toBeLessThanOrEqual(metrics.viewportWidth);
      expect(metrics.rail.width).toBeGreaterThan(0);
      expect(metrics.main.width).toBeGreaterThan(0);
      expect(metrics.panel.width).toBeGreaterThan(0);
    });
  }
});
