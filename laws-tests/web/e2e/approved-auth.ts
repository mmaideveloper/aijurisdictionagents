import fs from "node:fs";
import path from "node:path";
import { expect, type BrowserContext } from "@playwright/test";

// Actual central device proof and browser-bound exchange; no injected web sessions.
export async function approvedAuth(context: BrowserContext) {
  const base = "http://127.0.0.1:8410";
  const proof = JSON.parse(
    fs.readFileSync(
      path.resolve("../../runs/issue840/browser-authorization.json"),
      "utf8",
    ),
  );
  const start = await context.request.get(base + "/api/auth/start", {
    maxRedirects: 0,
  });
  expect(start.status()).toBe(303);
  const redirect = new URL(start.headers().location);
  const auth = await context.request.post(base + "/api/auth/authorize", {
    headers: { Origin: redirect.origin },
    data: { ...proof, state: redirect.searchParams.get("state") },
  });
  expect(auth.status()).toBe(200);
  await context.request.get((await auth.json()).redirect);
}
