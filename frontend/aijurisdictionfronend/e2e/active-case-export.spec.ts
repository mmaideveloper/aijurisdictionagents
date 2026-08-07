import { expect, test } from "@playwright/test";

const authUser = {
  userId: "user-active-export-e2e",
  email: "active-export@example.test",
  name: "Export Test User"
};

const cases = [
  {
    case_id: "case-active-export",
    user_id: authUser.userId,
    company_id: null,
    title: "Potvrdenie o prijatí peňazí",
    status: "in_progress",
    created_at: "2026-07-22T08:00:00Z",
    updated_at: "2026-07-22T08:05:00Z"
  },
  {
    case_id: "case-inactive-export",
    user_id: authUser.userId,
    company_id: null,
    title: "Druhý testovací prípad",
    status: "in_progress",
    created_at: "2026-07-22T09:00:00Z",
    updated_at: "2026-07-22T09:05:00Z"
  }
];

test.beforeEach(async ({ page }) => {
  await page.route("**/v1/cases?user_id=**", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(cases) })
  );
  await page.route("**/v1/cases/*/history?**", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ has_more: false, documents: [], messages: [] })
    })
  );
  await page.route("**/v1/cases/*/export?**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/zip",
      headers: {
        "Access-Control-Expose-Headers": "Content-Disposition",
        "Content-Disposition": 'attachment; filename="active-case-export.zip"'
      },
      body: "synthetic export"
    })
  );
  await page.addInitScript((user) => {
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
    window.localStorage.setItem("aj_frontend_lang", "sk");
  }, authUser);
});

test("shows and downloads export only from the active case card", async ({ page }) => {
  await page.goto("/app/assistant", { waitUntil: "domcontentloaded" });

  const firstCase = page.locator(".case-item-container").filter({ hasText: cases[0].title });
  const secondCase = page.locator(".case-item-container").filter({ hasText: cases[1].title });
  const exportButton = page.getByRole("button", { name: "Exportovať prípad" });

  await firstCase.locator(".case-item").click();
  await expect(firstCase.locator(".case-item")).toHaveClass(/active/);
  await expect(firstCase.getByRole("button", { name: "Exportovať prípad" })).toBeVisible();
  await expect(secondCase.getByRole("button", { name: "Exportovať prípad" })).toHaveCount(0);

  await page.screenshot({
    path: "../../runs/e2e/issue-565-active-case-export-button.png",
    fullPage: true
  });

  const exportResponse = page.waitForResponse((response) =>
    response.url().includes("/v1/cases/case-active-export/export?user_id=user-active-export-e2e")
  );
  const exportDownload = page.waitForEvent("download");
  await exportButton.click();
  await exportResponse;
  expect((await exportDownload).suggestedFilename()).toBe("active-case-export.zip");
  await expect(page.getByRole("status")).toHaveText("Sťahovanie exportu prípadu sa začalo.");

  await secondCase.locator(".case-item").click();
  await expect(secondCase.locator(".case-item")).toHaveClass(/active/);
  await expect(secondCase.getByRole("button", { name: "Exportovať prípad" })).toBeVisible();
  await expect(firstCase.getByRole("button", { name: "Exportovať prípad" })).toHaveCount(0);
});
