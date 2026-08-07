import { expect, test, type Page, type Route, type TestInfo } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";

const goldenQuestion =
  "Potrebujem pripraviť potvrdenie, že som 5. augusta 2026 prijal od Jána Testovacieho sumu 3 000 EUR v hotovosti ako úplné splatenie súkromnej pôžičky zo zmluvy uzatvorenej 10. januára 2026. Veriteľ je Peter Vzorový, dlžník Ján Testovací. Potvrdenie sa má podpísať v Bratislave a má jasne uvádzať, že pôžička je úplne splatená a veriteľ voči dlžníkovi nemá z nej žiadne ďalšie nároky. Aké údaje ešte potrebujete a môžete pripraviť návrh potvrdenia?";

const user = { userId: "issue-602-user", email: "issue-602@example.test", name: "Golden 602" };
const caseItem = {
  case_id: "issue-602-case",
  user_id: user.userId,
  company_id: null,
  title: "Golden test 01 – potvrdenie o splatení pôžičky",
  status: "in_progress",
  created_at: "2026-08-07T12:22:52Z",
  updated_at: "2026-08-07T12:24:51Z"
};
const documentItem = {
  doc_id: "issue-602-confirmation",
  kind: "generated_document",
  version: 1,
  original_filename: "potvrdenie_o_uplnom_splateni_pozicky.pdf",
  processing_status: "processed",
  processing_error: null,
  processed_at: "2026-08-07T12:24:51Z",
  created_at: "2026-08-07T12:24:51Z"
};

const documentDraft = `**Potvrdenie o úplnom splatení súkromnej pôžičky**

**1. Údaje o stranách**

| Strana | Údaje |
|---|---|
| **Veriteľ** | Peter Vzorový, Testová 200, Testovo, Slovensko |
| **Dlžník** | Ján Testovací, Testová 123, Testovo, Slovensko |

**2. Potvrdenie o splatení**

Peter Vzorový týmto potvrdzuje, že 5. augusta 2026 prijal v Bratislave od Jána Testovacieho sumu 3 000 EUR v hotovosti ako úplné a konečné splatenie súkromnej pôžičky zo zmluvy uzatvorenej 10. januára 2026.

---

**3. Zánik ďalších nárokov**

Veriteľ potvrdzuje, že pôžička je úplne splatená a voči dlžníkovi nemá z tejto pôžičky žiadne ďalšie nároky ani pohľadávky.

---

**4. Podpisy**

| Meno | Podpis | Dátum |
|---|---|---|
| Peter Vzorový | __________________ | 5. augusta 2026 |
| Ján Testovací | __________________ | 5. augusta 2026 |

---

**5. Kontrola pred podpisom**

Pred podpisom skontrolujte správnosť identifikačných údajov, dátumov a právne dôsledky potvrdenia.`;

const generatedLink =
  "/app/documents/view?caseId=issue-602-case&docId=issue-602-confirmation&kind=generated_document&filename=potvrdenie_o_uplnom_splateni_pozicky.pdf&caseTitle=Golden+test+01&userId=issue-602-user";
const hydratedContent = `Návrh potvrdenia je pripravený na vašu kontrolu.\n\n${documentDraft}\n\n**Čo ďalej?**\n\nPred podpisom overte správnosť údajov a právne dôsledky dokumentu.\n\nGenerated document:\n- [potvrdenie_o_uplnom_splateni_pozicky.pdf](${generatedLink})`;
const evidenceDirectory = process.env.GOLDEN_602_EVIDENCE_DIR?.trim();

const captureEvidence = async (page: Page, testInfo: TestInfo, filename: string) => {
  const body = await page.screenshot({ fullPage: true });
  await testInfo.attach(filename, { body, contentType: "image/png" });
  if (evidenceDirectory) {
    await mkdir(evidenceDirectory, { recursive: true });
    await page.screenshot({ path: path.join(evidenceDirectory, filename), fullPage: true });
  }
};

const fulfillJson = async (route: Route, body: unknown) => {
  await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
};

async function seedAuth(page: Page) {
  await page.addInitScript((authUser) => {
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(authUser));
    window.localStorage.setItem("aj_frontend_lang", "sk");
  }, user);
}

test("golden case 602 renders the complete Slovak Ollama Cloud draft and friendly HTML viewer", async ({
  page,
  context
}, testInfo) => {
  let generated = false;
  let emailRequest: Record<string, unknown> | null = null;

  await page.route("**/v1/model-routing/effective?**", (route) => fulfillJson(route, {
    plan_code: "unlimited",
    route_type: "selected_external",
    provider: "ollama_cloud",
    provider_display_name: "Ollama Cloud",
    model: "gpt-oss:20b",
    model_profile_id: "ollama_cloud_gpt_oss_20b",
    is_local: false,
    is_external: true,
    label: "Ollama Cloud – gpt-oss:20b"
  }));
  await page.route("**/v1/model-routing/selectable?**", (route) => fulfillJson(route, {
    eligible: true,
    profiles: [{
      model_profile_id: "ollama_cloud_gpt_oss_20b",
      provider: "ollama_cloud",
      provider_display_name: "Ollama Cloud",
      model: "gpt-oss:20b",
      label: "Ollama Cloud – gpt-oss:20b",
      is_local: false,
      is_external: true,
      eu_data_zone_capable: false,
      context_window_tokens: 128000
    }]
  }));
  await page.route("**/v1/cases?user_id=**", (route) => fulfillJson(route, [caseItem]));
  await page.route("**/v1/cases/issue-602-case/history?**", (route) => fulfillJson(route, {
    has_more: false,
    documents: generated ? [documentItem] : [],
    citations: [],
    messages: generated ? [
      { communication_id: "q-602", role: "user", content: goldenQuestion, agent_name: null, created_at: "2026-08-07T12:23:00Z" },
      { communication_id: "a-602", role: "assistant", content: hydratedContent, agent_name: "LawyerSlovakia", created_at: "2026-08-07T12:24:00Z" }
    ] : []
  }));
  await page.route("**/v1/chat/sessions", (route) => fulfillJson(route, {
    id: "issue-602-session",
    user_id: user.userId,
    case_id: caseItem.case_id,
    country: "SK",
    language: "sk",
    discussion_type: "advice",
    state: "active",
    selected_model_profile_id: "ollama_cloud_gpt_oss_20b",
    created_at: "2026-08-07T12:23:00Z"
  }));
  await page.route("**/v1/chat/sessions/issue-602-session/stream", async (route) => {
    generated = true;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: `event: message\ndata: ${JSON.stringify({ id: "a-602", session_id: "issue-602-session", role: "assistant", content: hydratedContent, agent_name: "LawyerSlovakia", created_at: "2026-08-07T12:24:00Z" })}\n\nevent: done\ndata: {"status":"completed"}\n\n`
    });
  });
  await context.route("**/v1/cases/issue-602-case/documents/issue-602-confirmation/pdf?**", (route) =>
    route.fulfill({ status: 200, contentType: "application/pdf", body: "%PDF-1.4\n%%EOF" })
  );
  await context.route("**/v1/cases/issue-602-case/documents/issue-602-confirmation?**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/plain; charset=utf-8",
      headers: { "Content-Disposition": 'inline; filename="potvrdenie_o_uplnom_splateni_pozicky.txt"' },
      body: documentDraft
    })
  );
  await context.route("**/v1/cases/issue-602-case/documents/send-email", async (route) => {
    emailRequest = route.request().postDataJSON() as Record<string, unknown>;
    await fulfillJson(route, {
      email_id: "email-602",
      recipient: "recipient@example.test",
      case_subject: caseItem.title,
      attachment_count: 0,
      correlation_id: "correlation-602",
      share_id: "share-602",
      share_url: "https://agent.jurisdigta.eu/shared-documents/golden602",
      expires_at: "2026-08-14T12:24:00Z"
    });
  });

  await seedAuth(page);
  await page.goto("/app/assistant", { waitUntil: "domcontentloaded" });
  await page.locator(".case-item").filter({ hasText: "Golden test 01" }).click();
  await page.getByRole("textbox", { name: "Správa asistentovi" }).fill(goldenQuestion);
  await page.getByRole("button", { name: "Odoslať správu" }).click();

  const preview = page.locator(".assistant-document-preview").first();
  await expect(preview).toBeVisible();
  await expect(preview).toContainText("1. Údaje o stranách");
  await expect(preview).toContainText("3. Zánik ďalších nárokov");
  await expect(preview).toContainText("4. Podpisy");
  await expect(preview).toContainText("5. Kontrola pred podpisom");
  await expect(preview).not.toContainText("**");
  await expect(page.locator(".assistant-thread__viewport")).not.toContainText("LawyerSlovakia");
  await expect(page.getByText("Náhľad dokumentu").first()).toBeVisible();

  const viewerPromise = context.waitForEvent("page");
  await page.getByLabel("Generated documents").getByRole("link").click();
  const viewer = await viewerPromise;
  await viewer.waitForLoadState("domcontentloaded");
  await expect(viewer.locator(".document-viewer-html-preview")).toBeVisible();
  await expect(viewer.locator(".document-viewer-html-preview")).toContainText("Zánik ďalších nárokov");
  await expect(viewer.locator("pre")).toHaveCount(0);
  await viewer.getByLabel("E-mail príjemcu").fill("recipient@example.test");
  await viewer.getByRole("button", { name: "Poslať e-mailom" }).click();
  await expect(viewer.getByText(/Odkaz na chránený dokument bol zaradený/)).toBeVisible();
  expect(emailRequest).toMatchObject({ recipient: "recipient@example.test", locale: "sk" });
  await captureEvidence(viewer, testInfo, "issue-602-complete-preview.png");
  await viewer.close();
});

test("golden case 602 renders the production document-share email sample", async ({ page }, testInfo) => {
  const emailPreviewPath = process.env.GOLDEN_602_EMAIL_PREVIEW?.trim();
  test.skip(!emailPreviewPath, "Set GOLDEN_602_EMAIL_PREVIEW to the generated HTML sample path.");
  await page.setContent(await readFile(emailPreviewPath as string, "utf-8"), { waitUntil: "load" });
  await expect(page.getByRole("link", { name: "Otvoriť chránený dokument" })).toBeVisible();
  await expect(page.getByRole("link", { name: /https:\/\/agent\.jurisdigta\.eu\/shared-documents\/golden602/ })).toBeVisible();
  await expect(page.locator("body")).not.toContainText("Professional legal workflow notification");
  await captureEvidence(page, testInfo, "issue-602-clickable-email-link.png");
});
