import { expect, Locator, Page, test } from "@playwright/test";

const identity = {
  userId: "mobile-auth-e2e-user",
  phone: "+421900123456",
  email: "mobile.auth@example.test",
  password: "E2e-only-password-123!",
  registrationCode: "123456",
  signInCode: "654321",
  deviceToken: "e2e-device-token"
};

async function enableFlutterSemantics(page: Page) {
  const placeholder = page.locator("flt-semantics-placeholder");
  await placeholder.click({ force: true, timeout: 60_000 });
  await expect(page.locator("flt-semantics").first()).toBeAttached();
}

async function enterFlutterText(locator: Locator, value: string) {
  await locator.click();
  await locator.press("Control+A");
  await locator.pressSequentially(value);
}

test("registers, signs out, and signs in with a controlled OTP", async ({ page }) => {
  const requests: Array<{ url: string; payload: Record<string, unknown> }> = [];

  await page.route("**/health", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok", database: { status: "ok" } })
    })
  );
  await page.route("**/v1/users/sign-up/send-code", async (route) => {
    requests.push({ url: route.request().url(), payload: route.request().postDataJSON() });
    await route.fulfill({ status: 202, contentType: "application/json", body: "{}" });
  });
  await page.route("**/v1/users/sign-up/complete", async (route) => {
    requests.push({ url: route.request().url(), payload: route.request().postDataJSON() });
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        user_id: identity.userId,
        phone_number: identity.phone,
        email: identity.email,
        first_name: "E2E",
        last_name: "User",
        data_processing_consent_at: "2026-07-12T12:00:00Z",
        data_processing_consent_version: "2026-05-06"
      })
    });
  });
  await page.route("**/v1/users/sign-in/send-code", async (route) => {
    requests.push({ url: route.request().url(), payload: route.request().postDataJSON() });
    await route.fulfill({ status: 202, contentType: "application/json", body: "{}" });
  });
  await page.route("**/v1/users/sign-in/verify-code", async (route) => {
    requests.push({ url: route.request().url(), payload: route.request().postDataJSON() });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user_id: identity.userId,
        phone_number: identity.phone,
        email: identity.email,
        first_name: "E2E",
        last_name: "User",
        device_auth_token: identity.deviceToken
      })
    });
  });
  await page.route("**/v1/users/**", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
      return;
    }
    await route.fallback();
  });
  await page.route("**/v1/cases**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
  );

  await page.goto("/");
  await enableFlutterSemantics(page);

  await page.getByText("Sign up", { exact: true }).click();
  await enterFlutterText(page.getByLabel("Phone number *"), identity.phone);
  await enterFlutterText(page.getByLabel("Email *"), identity.email);
  await enterFlutterText(page.getByLabel("Password *"), identity.password);
  await enterFlutterText(
    page.getByLabel("Verification code *"),
    identity.registrationCode
  );
  await page.getByText("Send code", { exact: true }).click();
  await page.getByRole("checkbox").click();
  await page.waitForTimeout(500);
  await page.screenshot({
    path: "artifacts/registration-form.png",
    fullPage: false
  });
  await page.getByText("Create account", { exact: true }).click();

  const signOutButton = page.getByRole("button", {
    name: /^(Sign out|Odhlásiť sa)$/
  });
  await expect(signOutButton).toBeVisible();
  await page.waitForTimeout(500);
  await page.screenshot({
    path: "artifacts/registration-complete.png",
    fullPage: false
  });
  expect(requests[0].payload).toEqual({ email: identity.email });
  expect(requests[1].payload).toMatchObject({
    phone_number: identity.phone,
    email: identity.email,
    password: identity.password,
    verification_code: identity.registrationCode,
    data_processing_consent_accepted: true
  });

  await signOutButton.click();
  await expect(page.getByLabel("Phone number")).toBeVisible();
  await enterFlutterText(page.getByLabel("Phone number"), identity.phone);
  await page.getByText("Send sign-in code", { exact: true }).click();
  await enterFlutterText(page.getByLabel("Sign-in code *"), identity.signInCode);
  await page.getByText("Sign in with code", { exact: true }).click();

  await expect(
    page.getByRole("button", { name: /^(Sign out|Odhlásiť sa)$/ })
  ).toBeVisible();
  await page.waitForTimeout(500);
  await page.screenshot({
    path: "artifacts/otp-login-complete.png",
    fullPage: false
  });
  expect(requests[2].payload).toMatchObject({ phone_number: identity.phone });
  expect(requests[2].payload).not.toHaveProperty("verification_code");
  expect(requests[3].payload).toMatchObject({
    phone_number: identity.phone,
    verification_code: identity.signInCode
  });
});
