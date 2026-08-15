import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { expect, test } from "@playwright/test";

const adminUser = {
  userId: "issue-617-admin",
  deviceId: "issue-617-device",
  deviceAuthToken: "synthetic-device-token",
  email: "issue-617-admin@example.test",
  name: "Issue 617 Admin",
  role: "admin",
  isEnabled: true
};

const emptyDashboard = {
  providers: [],
  profiles: [],
  credentials: [],
  policies: [],
  groups: [],
  memberships: [],
  users: [],
  users_page: { total: 0, limit: 25, offset: 0 },
  audit_events: [],
  route_priority: [],
  compliance_notes: [],
  grafana_url: "https://admin.jurisdigta.eu/grafana/"
};

test("an Admin sidebar click retries a failed dashboard request and shows a confirmed empty result", async ({ page }) => {
  let dashboardRequestCount = 0;
  let authenticatedRetry = false;

  await page.route("**/v1/admin/ai-models", async (route) => {
    dashboardRequestCount += 1;
    if (dashboardRequestCount === 1) {
      await route.abort("failed");
      return;
    }

    const headers = route.request().headers();
    authenticatedRetry =
      headers["x-jurisdigta-admin-user-id"] === adminUser.userId &&
      headers["x-jurisdigta-device-token"] === adminUser.deviceAuthToken;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(emptyDashboard) });
  });
  await page.route("**/v1/admin/ai-models/ollama/models", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ base_url: "http://127.0.0.1:11434", models: [] })
    });
  });

  await page.addInitScript((user) => {
    window.localStorage.setItem("aj_frontend_lang", "en");
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
  }, adminUser);

  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto("/app/admin", { waitUntil: "domcontentloaded" });

  await expect(page.getByRole("alert")).toContainText("Failed to fetch");
  await expect(page.getByText("No users found.")).toHaveCount(0);

  await page.getByRole("button", { name: "Users" }).click();

  await expect(page.getByText("No users found.")).toBeVisible();
  await expect(page.getByText("0-0 of 0")).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(dashboardRequestCount).toBe(2);
  expect(authenticatedRetry).toBe(true);

  const evidenceDirectory = path.resolve(process.cwd(), "../../runs/e2e/issue-617");
  const screenshotPath = path.join(evidenceDirectory, "01-admin-users-empty-after-retry.png");
  await mkdir(evidenceDirectory, { recursive: true });
  await page.screenshot({ path: screenshotPath, fullPage: true });
  await writeFile(
    path.join(evidenceDirectory, "result.json"),
    `${JSON.stringify({
      issue: 617,
      scenario: "admin-sidebar-retry-after-dashboard-fetch-failure",
      dashboardRequestCount,
      authenticatedRetry,
      finalState: "confirmed-empty-users",
      syntheticDataOnly: true,
      screenshot: path.basename(screenshotPath)
    }, null, 2)}\n`,
    "utf8"
  );
});
