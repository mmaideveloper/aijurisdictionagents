import { expect, test, type Locator, type Page } from '@playwright/test';

const authSessionKey = 'jurisdigta.web.auth.user.v1';

type Bounds = {
  left: number;
  right: number;
  top: number;
  bottom: number;
  width: number;
  height: number;
};

async function authenticate(page: Page) {
  await page.addInitScript(
    ({ key }) => {
      window.sessionStorage.setItem(
        key,
        JSON.stringify({
          userId: 'layout-test-user',
          email: 'layout-test@example.test',
          name: 'Layout Test User',
          role: 'JurisDigta user',
        }),
      );
    },
    { key: authSessionKey },
  );
}

async function getBounds(locator: Locator): Promise<Bounds> {
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  return {
    left: box!.x,
    right: box!.x + box!.width,
    top: box!.y,
    bottom: box!.y + box!.height,
    width: box!.width,
    height: box!.height,
  };
}

async function createCaseAndAssertLayout(page: Page, viewport: { width: number; height: number }, testInfoTitle: string) {
  await page.setViewportSize(viewport);
  await authenticate(page);
  await page.goto('/app/case');

  await page.getByLabel('Case name').fill(`Layout case ${viewport.width}x${viewport.height}`);
  await page.getByLabel('Jurisdiction').fill('Slovakia');
  await page.getByLabel('Opposing party').fill('Synthetic Counterparty');
  await page.getByRole('button', { name: 'Start AI lawyer chat' }).click();

  await expect(page).toHaveURL(/\/app\/chat$/);
  await expect(
    page.getByRole('heading', { name: `Layout case ${viewport.width}x${viewport.height}` }),
  ).toBeVisible();

  const sidebar = page.locator('.workspace-panel--left');
  const center = page.locator('.workspace-center');
  const config = page.locator('.workspace-panel--right');

  await expect(sidebar).toBeVisible();
  await expect(center).toBeVisible();
  await expect(config).toBeVisible();

  const sidebarBounds = await getBounds(sidebar);
  const centerBounds = await getBounds(center);
  const configBounds = await getBounds(config);

  expect(sidebarBounds.right).toBeLessThanOrEqual(centerBounds.left + 1);
  expect(centerBounds.right).toBeLessThanOrEqual(configBounds.left + 1);
  expect(configBounds.right).toBeLessThanOrEqual(viewport.width + 1);
  expect(centerBounds.width).toBeGreaterThan(240);
  expect(configBounds.width).toBeGreaterThan(220);

  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 1,
  );
  expect(hasHorizontalOverflow).toBe(false);

  await test.info().attach(`case-chat-layout-${testInfoTitle}.png`, {
    body: await page.screenshot({ fullPage: true }),
    contentType: 'image/png',
  });
}

test('new case opens non-overlapping chat workspace at 1638x942', async ({ page }, testInfo) => {
  await createCaseAndAssertLayout(page, { width: 1638, height: 942 }, testInfo.title);
});

test('new case opens non-overlapping chat workspace at 1280x720', async ({ page }, testInfo) => {
  await createCaseAndAssertLayout(page, { width: 1280, height: 720 }, testInfo.title);
});
