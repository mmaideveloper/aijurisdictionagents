import { expect, Locator, Page, test } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { getDocument } from "pdfjs-dist/legacy/build/pdf.mjs";

const spokenText =
  "Priprav mi potvrdenie o zaplatení 5000 eur Jankovi Hraškovi, adresa Testovo 10, splatné do konca roka.";
const identity = {
  userId: "audio-e2e-user",
  phone: "+421900555000",
  code: "246810"
};
const caseId = "audio-payment-case";
const sessionId = "audio-payment-session";
const documentId = "payment-confirmation-document";
const artifacts = path.resolve("artifacts");

async function enableFlutterSemantics(page: Page) {
  await page.locator("flt-semantics-placeholder").click({ force: true, timeout: 60_000 });
  await expect(page.locator("flt-semantics").first()).toBeAttached();
}

async function enterFlutterText(locator: Locator, value: string) {
  await locator.click();
  await locator.press("Control+A");
  await locator.pressSequentially(value);
}

async function installControlledSpeechRecognition(page: Page) {
  await page.addInitScript((transcript) => {
    class ControlledSpeechRecognition {
      continuous = false;
      interimResults = false;
      lang = "sk-SK";
      onstart: ((event: Event) => void) | null = null;
      onspeechstart: ((event: Event) => void) | null = null;
      onresult: ((event: unknown) => void) | null = null;
      onend: ((event: Event) => void) | null = null;
      onerror: ((event: unknown) => void) | null = null;
      onnomatch: ((event: Event) => void) | null = null;

      start() {
        const state = window as Window & { __controlledSpeechStarts?: number };
        state.__controlledSpeechStarts = (state.__controlledSpeechStarts ?? 0) + 1;
        const event = new Event("start");
        this.onstart?.(event);
        this.onspeechstart?.(event);
        window.setTimeout(() => {
          const alternative = { transcript, confidence: 0.99 };
          const recognitionResult = {
            0: alternative,
            length: 1,
            isFinal: true,
            item: (index: number) => (index === 0 ? alternative : null)
          };
          const results = {
            0: recognitionResult,
            length: 1,
            item: (index: number) => (index === 0 ? recognitionResult : null)
          };
          const resultEvent = new Event("result") as Event & {
            results?: typeof results;
            resultIndex?: number;
          };
          Object.defineProperties(resultEvent, {
            results: { value: results },
            resultIndex: { value: 0 }
          });
          this.onresult?.(resultEvent);
        }, 450);
      }

      stop() {
        this.onend?.(new Event("end"));
      }

      abort() {
        this.onend?.(new Event("end"));
      }
    }

    Object.defineProperty(window, "webkitSpeechRecognition", {
      configurable: true,
      value: ControlledSpeechRecognition
    });
    Object.defineProperty(window, "SpeechRecognition", {
      configurable: true,
      value: ControlledSpeechRecognition
    });
  }, spokenText);
}

test("login, synthetic audio transcript, system submit, preview, and PDF", async ({ page }) => {
  await mkdir(artifacts, { recursive: true });
  const submittedMessages: string[] = [];
  const pdf = await readFile(path.join(artifacts, "04-payment-confirmation.pdf"));

  await installControlledSpeechRecognition(page);
  await page.route("**/health", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: '{"status":"ok"}' })
  );
  await page.route("**/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathname = url.pathname;
    const cors = { "access-control-allow-origin": "*" };

    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: cors });
      return;
    }
    if (pathname === "/v1/users/sign-in/send-code") {
      await route.fulfill({ status: 202, headers: cors, contentType: "application/json", body: "{}" });
      return;
    }
    if (pathname === "/v1/users/sign-in/verify-code") {
      await route.fulfill({
        status: 200,
        headers: cors,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: identity.userId,
          phone_number: identity.phone,
          email: "audio.e2e@example.test",
          first_name: "Audio",
          last_name: "E2E",
          data_processing_consent_at: "2026-08-03T08:00:00Z",
          data_processing_consent_version: "2026-05-06",
          device_auth_token: "controlled-browser-token"
        })
      });
      return;
    }
    if (pathname === "/v1/cases" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        headers: cors,
        contentType: "application/json",
        body: JSON.stringify([{ case_id: caseId, title: "Testovacie potvrdenie", status: "open" }])
      });
      return;
    }
    if (pathname === `/v1/cases/${caseId}/history`) {
      await route.fulfill({
        status: 200,
        headers: cors,
        contentType: "application/json",
        body: JSON.stringify({ messages: [], documents: [], has_more: false })
      });
      return;
    }
    if (pathname === "/v1/chat/sessions") {
      await route.fulfill({
        status: 201,
        headers: cors,
        contentType: "application/json",
        body: JSON.stringify({ id: sessionId })
      });
      return;
    }
    if (pathname === `/v1/chat/sessions/${sessionId}/stream`) {
      const payload = request.postDataJSON() as { instruction?: string };
      submittedMessages.push(payload.instruction ?? "");
      const generatedUrl = `/v1/cases/${caseId}/documents/${documentId}/pdf?user_id=${identity.userId}`;
      const events = [
        `event: message\ndata: ${JSON.stringify({ role: "assistant", content: "Potvrdenie o zaplatení je pripravené na kontrolu.", generated_document_urls: [generatedUrl] })}`,
        `event: result\ndata: ${JSON.stringify({ final_recommendation: "Skontrolujte návrh pred podpisom.", judge_rationale: "Syntetický E2E výsledok.", metadata: { document_ready: true } })}`,
        "event: done\ndata: {}"
      ].join("\n\n") + "\n\n";
      await route.fulfill({ status: 200, headers: cors, contentType: "text/event-stream", body: events });
      return;
    }
    if (pathname === `/v1/chat/sessions/${sessionId}/result`) {
      await route.fulfill({
        status: 200,
        headers: cors,
        contentType: "application/json",
        body: JSON.stringify({
          final_recommendation: "Skontrolujte návrh pred podpisom.",
          judge_rationale: "Syntetický E2E výsledok.",
          metadata: { document_ready: true }
        })
      });
      return;
    }
    if (pathname === `/v1/chat/sessions/${sessionId}/export/documents`) {
      await route.fulfill({
        status: 200,
        headers: cors,
        contentType: "application/json",
        body: JSON.stringify({ documents: [{ index: 0, filename: "potvrdenie-o-zaplateni.pdf", title: "Potvrdenie o zaplatení" }] })
      });
      return;
    }
    if (pathname === `/v1/chat/sessions/${sessionId}/export/documents/0`) {
      await route.fulfill({
        status: 200,
        headers: {
          ...cors,
          "content-disposition": 'attachment; filename="potvrdenie-o-zaplateni.pdf"'
        },
        contentType: "application/pdf",
        body: pdf
      });
      return;
    }
    if (pathname.startsWith("/v1/users/") && request.method() === "GET") {
      await route.fulfill({ status: 200, headers: cors, contentType: "application/json", body: "[]" });
      return;
    }
    await route.fulfill({ status: 200, headers: cors, contentType: "application/json", body: "{}" });
  });

  await page.goto("/");
  await enableFlutterSemantics(page);
  await enterFlutterText(page.getByLabel("Phone number"), identity.phone);
  await page.getByText("Send sign-in code", { exact: true }).click();
  await enterFlutterText(page.getByLabel("Sign-in code *"), identity.code);
  await page.getByText("Sign in with code", { exact: true }).click();
  await expect(
    page.getByRole("button", { name: /^(Sign out|Odhlásiť sa)$/ })
  ).toBeVisible();
  await expect(page.getByText("Testovacie potvrdenie", { exact: true })).toBeVisible();

  const mic = page.getByRole("button", {
    name: /^(Add question\/answer by speech|Pridať otázku alebo odpoveď hlasom)$/
  });
  await mic.click();
  // The first click may only enable voice input while the ready prompt is
  // completing. A second click starts recognition once the toggle is on.
  await page.waitForTimeout(750);
  if (await mic.isVisible()) {
    await mic.click();
  }
  await expect.poll(() =>
    page.evaluate(() =>
      (window as Window & { __controlledSpeechStarts?: number })
        .__controlledSpeechStarts ?? 0
    )
  ).toBeGreaterThan(0);
  await expect(page.getByRole("button", {
    name: /Stop speech input|Zastaviť hlasový vstup/
  })).toBeVisible();
  const composer = page.getByRole("textbox");
  await expect(composer).toHaveValue(spokenText);
  await page.screenshot({ path: path.join(artifacts, "01-audio-transcript.png") });

  // Sending while listening is the supported app flow: it stops recognition
  // and submits the reviewed draft in one user action.
  await page.getByRole("button", { name: /^(Send to API|Odoslať do API)$/ }).click();
  await expect.poll(() => submittedMessages).toEqual([spokenText]);
  await page.screenshot({ path: path.join(artifacts, "02-message-submitted.png") });

  const exportDocuments = page.getByRole("button", {
    name: /^(Export documents|Dokumenty)$/
  });
  await expect(exportDocuments).toBeEnabled();
  await page.getByText("AIJurisDigta", { exact: true }).click({ force: true });
  await expect(
    page.getByText("Potvrdenie o zaplatení je pripravené na kontrolu.")
  ).toBeVisible();
  await page.screenshot({ path: path.join(artifacts, "03-document-preview.png") });

  const downloadPromise = page.waitForEvent("download");
  await exportDocuments.click({ force: true });
  const download = await downloadPromise;
  await download.saveAs(path.join(artifacts, "04-payment-confirmation.pdf"));
  const downloadedPdf = await readFile(path.join(artifacts, "04-payment-confirmation.pdf"));
  expect(downloadedPdf.subarray(0, 5).toString("ascii")).toBe("%PDF-");
  expect(downloadedPdf.length).toBeGreaterThan(1000);
  const parsedPdf = await getDocument({ data: new Uint8Array(downloadedPdf) }).promise;
  expect(parsedPdf.numPages).toBe(1);
  const firstPage = await parsedPdf.getPage(1);
  const textContent = await firstPage.getTextContent();
  const extractedText = textContent.items
    .map((item) => ("str" in item ? item.str : ""))
    .join(" ")
    .replace(/\s+/g, " ");
  for (const expectedText of [
    "Potvrdenie o zaplatení",
    "5 000 EUR",
    "Janko Hraško",
    "Testovo 10",
    "do konca roka",
    "VYŽADUJE ĽUDSKÚ KONTROLU"
  ]) {
    expect(extractedText).toContain(expectedText);
  }

  await writeFile(
    path.join(artifacts, "result-manifest.json"),
    JSON.stringify({
      scenario: "mobile-audio-payment-confirmation-sk",
      status: "passed",
      syntheticAudio: true,
      sttBoundary: "controlled-browser-web-speech",
      transcriptMatchedSubmittedMessage: true,
      pdfSignatureValid: true,
      pdfPageCount: parsedPdf.numPages,
      pdfExpectedTextValid: true,
      humanReviewRequired: true,
      retainedRawAudio: false,
      retentionDays: 7
    }, null, 2)
  );
});
