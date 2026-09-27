import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const root = path.resolve("../..");
const out = path.join(root, "runs/issue840/evidence");
const python = process.env.LAWS_TEST_E2E_PYTHON || path.join(root, "conda", "python.exe");

test("anonymous law links open the pinned provision in a new desktop and mobile tab", async ({ browser, request }) => {
  const fixture = JSON.parse(fs.readFileSync(path.join(root, "runs/issue840/reader-fixture.json"), "utf8"));
  const query = `test=${fixture.run_id}&section=4&paragraph=2&letter=j`;
  const direct = await request.get(`/api/laws/2026/9998?${query}`);
  expect(direct.ok()).toBeTruthy();
  const law = await direct.json();
  expect(law.version_id).toBe(fixture.version_id);
  expect(law.document_id).toBe(fixture.source_id);
  const highlighted = law.provisions.filter((p: any) => p.highlighted);
  expect(highlighted).toHaveLength(1);
  expect(highlighted[0].anchor).toBe("paragraf-4.odsek-2.pismeno-j.text");
  const manifest = {
    runId: fixture.run_id, status: "running", scope: "Public deterministic reader; no authentication or model invocation",
    expectedSource: fixture.source_id, observedSource: law.document_id,
    expectedVersion: fixture.version_id, observedVersion: law.version_id,
    services: ["laws-tests-web:8410", "laws-tests-api:8411", "local-postgresql:5440"],
    provider: "not invoked (deterministic link and database read)",
    retention: "14 days; synthetic database records removed after screenshots",
    screenshots: [] as string[],
  };
  fs.mkdirSync(out, { recursive: true });
  try {
    for (const [name, viewport] of [["desktop", { width: 1440, height: 1050 }], ["mobile", { width: 390, height: 844 }]] as const) {
      const context = await browser.newContext({ viewport });
      const page = await context.newPage();
      await page.goto(`/?test=${fixture.run_id}&question=${fixture.run_id}`);
      await expect(page.getByRole("heading", { name: "Overenie odkazu na zákon", exact: true })).toBeVisible();
      await page.getByRole("button", { name: "Pôvodná odpoveď" }).click();
      const link = page.locator("h3 a.legal-link").filter({ hasText: "§ 4" });
      await expect(link).toHaveAttribute("target", "_blank");
      const answerLink = page.locator(".answer-text a.legal-link");
      await expect(answerLink).toHaveAttribute("href", await link.getAttribute("href") as string);
      await page.screenshot({ path: path.join(out, `08-${name}-law-links.png`), fullPage: true });
      const popupPromise = page.waitForEvent("popup");
      await (name === "mobile" ? answerLink : link).click();
      const popup = await popupPromise;
      await expect(popup.locator(".law-provision.highlighted")).toHaveCount(1);
      await expect(popup.locator(".law-provision.highlighted")).toContainText(highlighted[0].body_text);
      await expect(popup.locator("body")).not.toContainText("FUTURE_VERSION");
      await expect(popup.getByText("2026-06-01", { exact: true })).toBeVisible();
      expect(await popup.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
      expect((await context.cookies()).some(c => c.name === "laws_session")).toBeFalsy();
      const screenshot = `09-${name}-law-provision.png`;
      await popup.screenshot({ path: path.join(out, screenshot), fullPage: true });
      manifest.screenshots.push(`08-${name}-law-links.png`, screenshot);
      await popup.goto(`/laws/2026/9998?test=${fixture.run_id}&section=4&paragraph=2&letter=z`);
      await expect(popup.getByRole("status")).toContainText("nepodarilo nájsť");
      await expect(popup.locator(".law-provision.highlighted")).toHaveCount(0);
      await popup.goto("/laws/2003/190?test=firearms-sk-2026");
      await expect(popup.getByRole("alert")).toContainText("schválený právny dátum");
      await page.goto(`/?test=${fixture.run_id}-preview&question=${fixture.run_id}-preview`);
      await expect(page.getByText("Neúplná skúšobná sada", { exact: true })).toBeVisible();
      await expect(page.getByRole("note")).toContainText("bez právneho overenia");
      await expect(page.getByRole("heading", { name: "Ukážková otázka", exact: true })).toBeVisible();
      await expect(page.getByText("Overený obsah", { exact: true })).toHaveCount(0);
      await page.screenshot({ path: path.join(out, `10-${name}-public-preview.png`), fullPage: true });
      manifest.screenshots.push(`10-${name}-public-preview.png`);
      await context.close();
    }
    manifest.status = "passed";
  } finally {
    fs.writeFileSync(path.join(out, "law-reader-manifest.json"), JSON.stringify(manifest, null, 2));
    execFileSync(python, ["laws-tests/tests/reader_fixture.py", "cleanup"], { cwd: root, env: { ...process.env, PYTHONPATH: path.join(root, "laws-tests/api") } });
  }
});
