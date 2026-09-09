import { expect, test } from "@playwright/test";

test("registration article plays the narrated Short and exposes Slovak captions", async ({ page, request }, testInfo) => {
  await page.goto("/#article-registracia-krok-za-krokom");
  await expect(page.getByRole("heading", { name: "Ako sa zaregistrovať do JurisDigta", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Otvoriť aplikáciu a registráciu" })).toHaveAttribute("href", "https://agent.jurisdigta.eu/auth");
  const video = page.locator(".article-video");
  await expect(video.locator("source")).toHaveAttribute("src", "assets/jurisdigta-registracia-sk.mp4");
  await expect(video.locator("track")).toHaveAttribute("srclang", "sk");
  await expect.poll(() => video.evaluate((element: HTMLVideoElement) => ({
    width: element.videoWidth, height: element.videoHeight, duration: element.duration,
    muted: element.muted, paused: element.paused, autoplay: element.autoplay
  }))).toEqual({ width: 1080, height: 1920, duration: 15, muted: false, paused: true, autoplay: false });
  const captions = await request.get("/assets/jurisdigta-registracia-sk.vtt");
  expect(captions.ok()).toBeTruthy();
  expect(captions.headers()["content-type"]).toContain("text/vtt");
  expect(await captions.text()).toContain("Vyplňte telefón, e-mail a heslo.");
  await video.click();
  await video.evaluate(async (element: HTMLVideoElement) => { await element.play(); });
  await expect.poll(() => video.evaluate((element: HTMLVideoElement) => element.currentTime)).toBeGreaterThan(0.2);
  await video.evaluate((element: HTMLVideoElement) => { element.pause(); element.currentTime = 5; });
  await expect.poll(() => video.evaluate((element: HTMLVideoElement) => element.seeking)).toBe(false);
  await video.scrollIntoViewIfNeeded();
  await page.locator("#article-detail-view").screenshot({ path: testInfo.outputPath("registration-article.png") });
  await page.screenshot({ path: testInfo.outputPath("registration-viewport.png") });
});
