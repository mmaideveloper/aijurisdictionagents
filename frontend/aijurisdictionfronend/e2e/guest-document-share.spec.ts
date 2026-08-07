import { BrowserContext, expect, test } from "@playwright/test";

const sender = {
  userId: "guest-share-sender-e2e",
  email: "sender@example.test",
  name: "Synthetic Sender"
};

const caseId = "guest-share-case-e2e";
const documentId = "guest-share-document-e2e";
const shareId = "guest-share-e2e";
const shareToken = "opaque-guest-share-token-e2e";
const verificationCode = "557123";
const sessionToken = "opaque-pdf-session-e2e";
const pdfBody = "%PDF-1.4\n% synthetic guest document\n1 0 obj\n<<>>\nendobj\n%%EOF";

test("an unregistered recipient opens a generated PDF through the frontend share link", async ({
  browser,
  page
}) => {
  let generatedShareUrl = "";
  let sharedDocumentIds: string[] = [];

  await page.addInitScript((user) => {
    window.sessionStorage.setItem("jurisdigta.web.auth.user.v1", JSON.stringify(user));
    window.localStorage.setItem("aj_frontend_lang", "en");
  }, sender);

  await page.route(`**/v1/cases/${caseId}/documents/${documentId}/pdf?**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/pdf",
      headers: { "Content-Disposition": 'inline; filename="synthetic-share.pdf"' },
      body: pdfBody
    });
  });
  await page.route(`**/v1/cases/${caseId}/documents/${documentId}?**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/plain",
      headers: { "Content-Disposition": 'inline; filename="synthetic-share.txt"' },
      body: "Synthetic legal document for guest-share E2E verification."
    });
  });
  await page.route(`**/v1/cases/${caseId}/documents/send-email`, async (route) => {
    const payload = route.request().postDataJSON() as { doc_ids?: string[] };
    sharedDocumentIds = payload.doc_ids ?? [];
    generatedShareUrl = new URL(`/shared-documents/${shareToken}`, page.url()).toString();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        email_id: "guest-share-email-e2e",
        recipient: "unregistered-recipient@example.test",
        case_subject: "Synthetic guest-share case",
        attachment_count: 0,
        correlation_id: "guest-share-correlation-e2e",
        share_id: shareId,
        share_url: generatedShareUrl,
        expires_at: "2030-01-01T00:00:00Z"
      })
    });
  });

  await page.goto(
    `/app/documents/view?caseId=${caseId}&docId=${documentId}` +
      "&kind=generated_document&filename=synthetic-share.pdf" +
      "&caseTitle=Synthetic+guest-share+case"
  );
  await expect(page.locator(".document-viewer-title strong")).toHaveText("synthetic-share.pdf");
  await page.getByLabel("Recipient email").fill("unregistered-recipient@example.test");
  await page.getByRole("button", { name: "Send by email" }).click();
  await expect(
    page.getByText("Protected document link queued. The recipient must verify by email.")
  ).toBeVisible();

  expect(sharedDocumentIds).toEqual([documentId]);
  expect(generatedShareUrl).toContain(`/shared-documents/${shareToken}`);

  const guestContext = await browser.newContext();
  try {
    await guestContext.addInitScript(() => {
      window.localStorage.setItem("aj_frontend_lang", "en");
    });
    await configureGuestApi(guestContext);
    const guestPage = await guestContext.newPage();
    await guestPage.goto(generatedShareUrl);

    expect(
      await guestPage.evaluate(() =>
        window.sessionStorage.getItem("jurisdigta.web.auth.user.v1")
      )
    ).toBeNull();
    await expect(guestPage).toHaveURL(new RegExp(`/shared-documents/${shareToken}$`));
    await expect(
      guestPage.getByRole("heading", { name: "Protected legal document" })
    ).toBeVisible();

    await guestPage.getByRole("button", { name: "Send verification code" }).click();
    await expect(
      guestPage.getByText("A verification code was sent to the recipient email.")
    ).toBeVisible();
    await guestPage.getByLabel("Six-digit verification code").fill(verificationCode);
    await guestPage.getByRole("button", { name: "Verify and open document" }).click();

    const viewer = guestPage.locator("iframe.document-viewer-frame");
    await expect(viewer).toBeVisible();
    await expect(viewer).toHaveAttribute("src", /^blob:/);
    await expect(guestPage).not.toHaveURL(/\/auth/);
    await expect(
      guestPage.getByText(
        "AI-assisted legal documents require qualified human review before filing, signing, or reliance."
      )
    ).toBeVisible();
  } finally {
    await guestContext.close();
  }
});

async function configureGuestApi(context: BrowserContext): Promise<void> {
  await context.route(`**/v1/document-shares/${shareToken}/request-code`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ message: "Verification code sent.", locale: "en" })
    });
  });
  await context.route(`**/v1/document-shares/${shareToken}/verify`, async (route) => {
    const payload = route.request().postDataJSON() as { code?: string };
    expect(payload.code).toBe(verificationCode);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        session_token: sessionToken,
        expires_at: "2030-01-01T00:30:00Z",
        locale: "en"
      })
    });
  });
  await context.route("**/v1/document-shares/content/pdf", async (route) => {
    expect(route.request().headers().authorization).toBe(`Bearer ${sessionToken}`);
    await route.fulfill({
      status: 200,
      contentType: "application/pdf",
      headers: {
        "Cache-Control": "no-store, max-age=0",
        "Referrer-Policy": "no-referrer",
        "Content-Disposition": 'inline; filename="document.pdf"'
      },
      body: pdfBody
    });
  });
}
