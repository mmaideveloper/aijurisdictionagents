import { expect, test } from "@playwright/test";

test("publishes the reviewed Slovak consumer video only in its blog article", async ({
  page
}, testInfo) => {
  await page.setViewportSize({ width: 689, height: 856 });
  await page.goto("/#article-pravna-pomoc-pre-kazdeho", {
    waitUntil: "domcontentloaded"
  });

  await expect(page.getByRole("heading", {
    name: "Základná právna orientácia pre každého"
  })).toBeVisible();
  const video = page.locator(".article-video");
  const source = video.locator("source");
  await expect(source).toHaveAttribute(
    "src",
    "assets/jurisdigta-pravna-pomoc-sk.mp4"
  );
  await expect(page.locator("#jurisdigta-video-source")).toHaveAttribute(
    "src",
    "assets/jurisdigta-sk.mp4"
  );

  await expect.poll(async () => video.evaluate((element: HTMLVideoElement) => ({
    duration: element.duration,
    height: element.videoHeight,
    readyState: element.readyState,
    width: element.videoWidth
  }))).toMatchObject({
    height: 1276,
    readyState: 4,
    width: 720
  });

  const duration = await video.evaluate((element: HTMLVideoElement) => element.duration);
  expect(duration).toBeGreaterThanOrEqual(12);
  expect(duration).toBeLessThanOrEqual(14);

  await video.evaluate(async (element: HTMLVideoElement) => {
    element.loop = false;
    element.playbackRate = 16;
    await element.play();
  });
  await expect.poll(async () => video.evaluate(
    (element: HTMLVideoElement) => Math.abs(element.currentTime - element.duration)
  )).toBeLessThan(0.5);
  await video.evaluate((element: HTMLVideoElement) => element.pause());

  await expect(video).toBeVisible();
  await video.screenshot({
    path: testInfo.outputPath("issue-734-slovak-video-end-card.png")
  });
});
