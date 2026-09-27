import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const root = path.resolve("../..");
const out = path.join(root, "runs/issue840/evidence");
fs.mkdirSync(out, { recursive: true });
test.afterEach(async ({}, info) => {
  if (info.status !== 'passed') {
    fs.writeFileSync(path.join(out,'result-manifest.json'),JSON.stringify({status:'failed',
      syntheticAttemptsCleaned:false,reason:'Inspect sanitized test output; this run is not acceptance evidence.'},null,2));
  }
});

test("public A20 desktop/mobile and real authenticated E1 evaluation", async ({
  page,
  browser,
}) => {
  const runId = "laws-tests-840-" + Date.now();
  const manifest: any = {
    runId,
    status: "running",
    services: [
      "laws-tests-web:8410",
      "laws-tests-api:8411",
      "jurisdigta-web:8412",
      "jurisdigta-api:8413",
      "mcp:8414",
      "local-postgresql:5440",
    ],
    expectedSources: ["A-20", "E-1"],
    observedSources: [],
    results: [],
    retention: "14 days; synthetic attempt records deleted after capture",
  };
  fs.writeFileSync(path.join(out,'result-manifest.json'),JSON.stringify(manifest,null,2));
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.goto("/?test=firearms-sk-2026&question=A-20");
  await expect(
    page.getByRole("heading", {
      name: "Vyhláška, preprava a správca strelnice",
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Prihlásiť sa", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Rozbaliť všetky odpovede" }).click();
  await expect(page.locator(".answer-text")).toHaveCount(3);
  await page.screenshot({
    path: path.join(out, "01-desktop-public-a20.png"),
    fullPage: true,
  });
  manifest.observedSources.push("A-20");
  const mobile = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });
  const mobilePage = await mobile.newPage();
  await mobilePage.goto("/?test=firearms-sk-2026&question=A-20");
  await expect(
    mobilePage.getByRole("button", { name: "Prihlásiť sa", exact: true }),
  ).toBeVisible();
  await mobilePage
    .getByRole("button", { name: "Rozbaliť všetky odpovede" })
    .click();
  await expect(mobilePage.locator(".answer-text")).toHaveCount(3);
  expect(
    await mobilePage.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await mobilePage.screenshot({
    path: path.join(out, "02-mobile-public-a20.png"),
    fullPage: true,
  });
  await mobilePage.screenshot({
    path: path.join(out, "02-mobile-public-a20-viewport.png"),
  });
  await mobile.close();
  await page.goto("/?test=firearms-sk-2026&question=E-1");
  await expect(
    page.getByRole("heading", { name: "Bezpečná manipulácia na strelnici" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Prihlásiť sa a precvičovať" })
    .click();
  await expect(page.locator("input[type=email]")).toBeVisible();
  const account = JSON.parse(
    fs.readFileSync(
      path.join(root, "runs/issue840/synthetic-account.json"),
      "utf8",
    ),
  );
  await page.locator("input[type=email]").fill(account.email);
  await page.locator("input[type=password]").fill(account.password);
  await page.locator("form button.primary").first().click();
  const otp = page.locator("input[inputmode=numeric]");
  await expect(otp).toBeVisible({ timeout: 30000 });
  // Read the real generated OTP from the synthetic local outbox; no mocked login.
  const code = execFileSync(
    path.join(root, "conda/python.exe"),
    [path.join(root, "laws-tests/tests/read_synthetic_otp.py")],
    { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
  ).trim();
  await otp.fill(code);
  await page.locator("form button.primary").first().click();
  await expect(
    page.getByRole("button", { name: "Pokračovať do testov" }),
  ).toBeVisible({ timeout: 30000 });
  await page.getByRole("button", { name: "Pokračovať do testov" }).click();
  await expect(page.getByRole("button", { name: "Odhlásiť sa" })).toBeVisible({
    timeout: 30000,
  });
  await page.getByRole("button", { name: "Precvičiť túto otázku" }).click();
  await expect(page.locator("textarea")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Pôvodná odpoveď" }),
  ).toHaveCount(0);
  const correct =
    "So zbraňou vždy zaobchádzam, akoby bola nabitá. Nikdy nemierim na ľudí. Mierim len do priestoru terčov, keď tam nie sú osoby. Neprekročím povolené vykláňanie 45 stupňov hore a dole a 90 stupňov doprava a doľava.";
  await page.locator("textarea").fill(correct);
  const goodResponse = page.waitForResponse(
    (r) => r.url().endsWith("/api/attempts") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Vyhodnotiť odpoveď" }).click();
  const good = await (await goodResponse).json();
  expect(good.status).toBe("completed");
  expect(good.passed).toBe(true);
  expect(good.provider).toBe("azurefoundry");
  expect(good.model).toBe("gpt-5-mini");
  await expect(page.getByText("✓ Úspešná odpoveď")).toBeVisible();
  await expect(
    page.getByText("Celkový výsledok: 100 % · Splnené"),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(out, "03-desktop-e1-correct.png"),
    fullPage: true,
  });
  manifest.results.push({
    scenario: "correct",
    attemptId: good.id,
    score: good.score,
    passed: good.passed,
    missing: good.result.missingPoints,
    provider: good.provider,
    model: good.model,
  });
  await page.getByRole("button", { name: "Skúsiť novú odpoveď" }).click();
  await page
    .locator("textarea")
    .fill(
      "Pravidlá bezpečnej manipulácie nepoznám. Neviem uviesť ani jedno pravidlo.",
    );
  const badResponse = page.waitForResponse(
    (r) => r.url().endsWith("/api/attempts") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Vyhodnotiť odpoveď" }).click();
  const bad = await (await badResponse).json();
  expect(bad.status).toBe("completed");
  expect(bad.passed).toBe(false);
  expect(bad.result.missingPoints.length).toBeGreaterThan(0);
  await expect(page.getByText("↗ Skúste doplniť odpoveď")).toBeVisible();
  await expect(
    page.getByText("Celkový výsledok: 0 % · Nesplnené"),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(out, "04-desktop-e1-incorrect.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: path.join(out, "05-mobile-e1-feedback.png"),
    fullPage: true,
  });
  manifest.results.push({
    scenario: "incorrect",
    attemptId: bad.id,
    score: bad.score,
    passed: bad.passed,
    missing: bad.result.missingPoints,
    provider: bad.provider,
    model: bad.model,
  });
  manifest.observedSources.push("E-1");
  await page.getByRole("button", { name: "Moje výsledky" }).click();
  await expect(page.locator(".history article")).toHaveCount(2);
  await page.reload();
  await page.getByRole("button", { name: "Moje výsledky" }).click();
  await expect(page.locator(".history article")).toHaveCount(2);
  await page.screenshot({
    path: path.join(out, "06-mobile-saved-history.png"),
    fullPage: true,
  });
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Odstrániť históriu" }).click();
  await expect(page.getByText("Zatiaľ nemáte uložené výsledky.")).toBeVisible();
  manifest.status = "passed";
  manifest.syntheticAttemptsCleaned = true;
  fs.writeFileSync(
    path.join(out, "result-manifest.json"),
    JSON.stringify(manifest, null, 2),
  );
});
