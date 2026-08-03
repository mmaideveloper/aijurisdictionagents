import { mkdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { chromium } from "@playwright/test";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourcePath = path.join(root, "fixtures", "payment-confirmation.html");
const artifacts = path.join(root, "artifacts");
const pdfPath = path.join(artifacts, "04-payment-confirmation.pdf");
const previewPath = path.join(artifacts, "05-pdf-first-page.png");

await mkdir(artifacts, { recursive: true });
const html = await readFile(sourcePath, "utf8");
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 940, height: 1329 } });
  await page.setContent(html, { waitUntil: "load" });
  await page.pdf({ path: pdfPath, format: "A4", printBackground: true });
  await page.screenshot({ path: previewPath, fullPage: true });
} finally {
  await browser.close();
}

const pdf = await readFile(pdfPath);
if (pdf.length < 1000 || pdf.subarray(0, 5).toString("ascii") !== "%PDF-") {
  throw new Error("Generated payment confirmation is not a valid PDF.");
}
console.log(`Generated PDF evidence (${pdf.length} bytes) and first-page preview.`);
