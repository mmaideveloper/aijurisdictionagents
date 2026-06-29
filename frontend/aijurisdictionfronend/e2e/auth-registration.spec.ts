import { expect, test } from "@playwright/test";

test("registration starts hidden and completes after email OTP verification", async ({ page }) => {
  let sendCodePayload: unknown;
  let completePayload: unknown;

  await page.route("**/v1/users/sign-up/send-code", async (route) => {
    sendCodePayload = route.request().postDataJSON();
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ status: "sent" })
    });
  });

  await page.route("**/v1/users/sign-up/complete", async (route) => {
    completePayload = route.request().postDataJSON();
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        user_id: "user-registration-e2e",
        phone_number: "+421900123456",
        email: "new@example.test",
        full_name: "new@example.test",
        role: "user",
        is_enabled: true
      })
    });
  });

  await page.route("**/v1/cases?user_id=**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([])
    });
  });

  await page.addInitScript(() => {
    window.localStorage.setItem("aj_frontend_lang", "en");
  });

  await page.goto("/auth", { waitUntil: "domcontentloaded" });

  await expect(page.getByRole("button", { name: "Sign up" })).toBeVisible();
  await expect(page.getByLabel("Phone number")).toBeHidden();
  await expect(page.getByLabel("OTP code")).toBeHidden();

  await page.getByRole("button", { name: "Sign up" }).click();

  await expect(page.getByLabel("Phone number")).toBeVisible();
  await expect(page.getByLabel("Work email")).toBeVisible();
  await expect(page.getByLabel("Password")).toBeVisible();
  await expect(page.getByLabel("OTP code")).toBeHidden();

  await page.getByLabel("Phone number").fill("+421900123456");
  await page.getByLabel("Work email").fill("new@example.test");
  await page.getByLabel("Password").fill("Secret123!");
  await page.getByRole("button", { name: "Continue to email verification" }).click();

  await expect(page.getByText("OTP code was sent to the selected email.")).toBeVisible();
  await expect(page.getByLabel("OTP code")).toBeVisible();
  expect(sendCodePayload).toEqual({ email: "new@example.test" });

  await page.getByLabel("OTP code").fill("123456");
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page).toHaveURL(/\/app\/assistant$/);
  expect(completePayload).toMatchObject({
    phone_number: "+421900123456",
    email: "new@example.test",
    password: "Secret123!",
    verification_code: "123456",
    data_processing_consent_accepted: true
  });
});
