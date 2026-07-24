/**
 * Minimal runnable verification for issue #576's corporate-theme E2E contract.
 *
 * Run:
 *   node examples/frontend_corporate_theme_issue_576_minimal_demo.mjs
 */

import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const specPath = resolve(
  repoRoot,
  "frontend",
  "aijurisdictionfronend",
  "e2e",
  "corporate-theme-visual.spec.ts"
);
const spec = await readFile(specPath, "utf8");

for (const requiredToken of [
  'primary: "#06397a"',
  'ink: "#082046"',
  'page.goto("/auth"',
  '"/login-shield.png"',
  "01-auth-corporate-theme.png",
  'toContain("Source Serif 4")'
]) {
  if (!spec.includes(requiredToken)) {
    throw new Error(`Missing E2E contract token ${JSON.stringify(requiredToken)} in ${specPath}`);
  }
}

console.log("Issue #576 corporate-theme E2E contract is present.");
console.log(
  "Run the browser check from frontend/aijurisdictionfronend with: " +
    "npx playwright test e2e/corporate-theme-visual.spec.ts"
);
