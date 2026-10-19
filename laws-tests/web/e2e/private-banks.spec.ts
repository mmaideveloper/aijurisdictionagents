import { test, expect, type BrowserContext, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const root = path.resolve("../..");
const folder = path.join(root, "runs/issue924");
const evidence = path.join(folder, "evidence");
const base = "http://127.0.0.1:8940";
test("private banks: actual approvals, PDF/image import, AI tags and real practice", async ({
  browser,
}) => {
  test.setTimeout(600000);
  const fixture = JSON.parse(
    fs.readFileSync(path.join(folder, "private-fixture.json"), "utf8"),
  );
  fs.mkdirSync(evidence, { recursive: true });
  const manifest: any = {
    runId: fixture.run,
    status: "running",
    services: [
      "tests-web:8940",
      "tests-api:8941",
      "bank-worker",
      `local-postgresql:${fixture.databasePort || 5494}`,
      "central-identity-adapter/local-postgresql",
    ],
    expectedSources: [101, 102, 103, 104],
    accessBoundary: [],
    observedSources: [],
    routes: [],
    retention:
      "14 days; synthetic database records and credentials removed after capture",
  };
  const contexts: BrowserContext[] = [];
  const save = () =>
    fs.writeFileSync(
      path.join(evidence, "result-manifest.json"),
      JSON.stringify(manifest, null, 2),
    );
  save();
  async function catalogueOnly(page: Page) {
    await expect(
      page.getByRole("heading", { name: /Vaše vedomosti/ }),
    ).toBeVisible();
    for (const name of ["Synthetic Medical 924", "Synthetic Firearms 924"])
      await expect(
        page.getByRole("heading", { name, exact: true }),
      ).toBeVisible();
    await expect(page.locator(".question-row")).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Otvoriť banku", exact: true }),
    ).toHaveCount(0);
    await expect(page.getByLabel("Vaša odpoveď")).toHaveCount(0);
    await expect(
      page.getByText("What is the chemical formula of water?", { exact: true }),
    ).toHaveCount(0);
    await expect(page.getByText("H2O", { exact: true })).toHaveCount(0);
  }
  async function deniedContent(context: BrowserContext, status: number) {
    for (const bank of fixture.banks) {
      for (const endpoint of [
        `/api/tests/${bank}/questions`,
        `/api/questions/${bank}-1`,
      ]) {
        const response = await context.request.get(base + endpoint);
        expect(response.status()).toBe(status);
        expect(await response.text()).not.toContain("H2O");
      }
    }
  }
  try {
    const visitor = await browser.newContext();
    contexts.push(visitor);
    const publicPage = await visitor.newPage();
    await publicPage.goto(base);
    await catalogueOnly(publicPage);
    await deniedContent(visitor, 401);
    const catalogue = await (
      await visitor.request.get(base + "/api/tests")
    ).text();
    expect(catalogue).not.toContain("What is the chemical formula of water?");
    expect(catalogue).not.toContain("H2O");
    await expect(
      publicPage.getByRole("button", {
        name: "Registrácia / prihlásenie",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      publicPage.getByRole("heading", { name: /Vaše vedomosti/ }),
    ).toBeVisible();
    expect(
      (
        await visitor.request.get(
          base + "/api/questions/" + fixture.banks[1] + "-1",
        )
      ).status(),
    ).toBe(401);
    await publicPage.screenshot({
      path: path.join(evidence, "01-public-catalogue.png"),
      fullPage: true,
    });
    await publicPage.goto(
      `${base}/?test=${fixture.banks[1]}&question=${fixture.banks[1]}-1`,
    );
    await catalogueOnly(publicPage);
    manifest.accessBoundary.push(
      "anonymous: catalogue only; direct question links and APIs denied",
    );
    async function sign(role: string) {
      const context = await browser.newContext({
        viewport: { width: 390, height: 844 },
      });
      contexts.push(context);
      const start = await context.request.get(base + "/api/auth/start", {
        maxRedirects: 0,
      });
      expect(start.status()).toBe(303);
      const location = new URL(start.headers().location);
      const auth = await context.request.post(base + "/api/auth/authorize", {
        headers: { Origin: location.origin },
        data: {
          state: location.searchParams.get("state"),
          ...Object.fromEntries(
            ["user_id", "device_id", "device_token"].map((k) => [
              k,
              fixture.users[role][k],
            ]),
          ),
        },
      });
      expect(auth.status()).toBe(200);
      await context.request.get((await auth.json()).redirect);
      const me = await (await context.request.get(base + "/api/me")).json();
      return { context, headers: { Origin: base, "X-CSRF-Token": me.csrf } };
    }
    const admin = await sign("admin");
    const learners: any = {};
    for (const role of ["firearms", "medical", "both"]) {
      const learner = await sign(role);
      learners[role] = learner;
      const pendingPage = await learner.context.newPage();
      await pendingPage.goto(base);
      await catalogueOnly(pendingPage);
      await deniedContent(learner.context, 403);
      if (role === "medical") {
        await pendingPage.screenshot({
          path: path.join(evidence, "11-registered-no-approval.png"),
          fullPage: true,
        });
        manifest.accessBoundary.push(
          "registered without approval: catalogue only; both banks denied",
        );
      }
      const ids =
        role === "both"
          ? fixture.banks
          : [fixture.banks[role === "firearms" ? 0 : 1]];
      expect(
        (
          await learner.context.request.post(
            base + "/api/access-requests/" + ids[0],
            { headers: learner.headers },
          )
        ).status(),
      ).toBe(200);
      await pendingPage.reload();
      await catalogueOnly(pendingPage);
      if (role === "medical") {
        await expect(
          pendingPage.getByText("Žiadosť čaká na schválenie.", { exact: true }),
        ).toBeVisible();
        await pendingPage.screenshot({
          path: path.join(evidence, "12-request-pending.png"),
          fullPage: true,
        });
        expect(
          (
            await admin.context.request.put(
              base + "/api/admin/users/" + fixture.users[role].user_id,
              {
                headers: admin.headers,
                data: { approved: true, bank_ids: [] },
              },
            )
          ).status(),
        ).toBe(200);
        await deniedContent(learner.context, 403);
        await pendingPage.goto(
          `${base}/?test=${fixture.banks[1]}&question=${fixture.banks[1]}-1`,
        );
        await catalogueOnly(pendingPage);
        manifest.accessBoundary.push(
          "globally approved without bank grant: question deep link and both banks denied",
        );
      }
      expect(
        (
          await learner.context.request.get(
            base + "/api/questions/" + ids[0] + "-1",
          )
        ).status(),
      ).toBe(403);
      expect(
        (
          await admin.context.request.put(
            base + "/api/admin/users/" + fixture.users[role].user_id,
            { headers: admin.headers, data: { approved: true, bank_ids: ids } },
          )
        ).status(),
      ).toBe(200);
      for (const id of fixture.banks)
        expect(
          (
            await learner.context.request.get(
              base + "/api/questions/" + id + "-1",
            )
          ).status(),
        ).toBe(ids.includes(id) ? 200 : 403);
      await pendingPage.goto(base);
      await expect(
        pendingPage.getByRole("button", { name: "Otvoriť banku", exact: true }),
      ).toHaveCount(ids.length);
      for (const id of fixture.banks) {
        const name =
          id === fixture.banks[0]
            ? "Synthetic Firearms 924"
            : "Synthetic Medical 924";
        const card = pendingPage.getByRole("article").filter({
          has: pendingPage.getByRole("heading", { name, exact: true }),
        });
        await expect(
          card.getByRole("button", { name: "Otvoriť banku", exact: true }),
        ).toHaveCount(ids.includes(id) ? 1 : 0);
        await pendingPage.goto(`${base}/?test=${id}&question=${id}-1`);
        if (ids.includes(id)) {
          await expect(
            pendingPage.getByText("What is the chemical formula of water?", {
              exact: true,
            }),
          ).toBeVisible();
        } else {
          await expect(
            pendingPage.getByRole("heading", { name: /Vaše vedomosti/ }),
          ).toBeVisible();
          await expect(
            pendingPage.getByText("What is the chemical formula of water?", {
              exact: true,
            }),
          ).toHaveCount(0);
        }
        await pendingPage.goto(base);
      }
      await expect(
        pendingPage.getByRole("button", { name: "Otvoriť banku", exact: true }),
      ).toHaveCount(ids.length);
      manifest.accessBoundary.push(
        `${role}: only explicitly approved bank links and questions open`,
      );
      if (role === "medical")
        await pendingPage.screenshot({
          path: path.join(evidence, "13-medical-only-approved.png"),
          fullPage: true,
        });
      await pendingPage.close();
    }
    const adminPage = await admin.context.newPage();
    await adminPage.goto(base);
    await adminPage
      .getByRole("button", { name: "Správa testov", exact: true })
      .click();
    await adminPage
      .getByRole("button", { name: "Žiadosti a schválení používatelia" })
      .click();
    await expect(
      adminPage.getByRole("heading", {
        name: "Účet " + fixture.users.medical.email,
      }),
    ).toBeVisible();
    expect(
      await adminPage.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await adminPage.screenshot({
      path: path.join(evidence, "02-mobile-admin-approvals.png"),
      fullPage: true,
    });
    const medical = fixture.banks[1];
    const importedIds: Record<number, string> = {};
    manifest.importedRecords = [];
    const bothCard = adminPage.getByRole("article").filter({
      has: adminPage.getByRole("heading", {
        name: "Účet " + fixture.users.both.email,
      }),
    });
    await expect(
      bothCard.getByRole("checkbox", {
        name: "Synthetic Medical 924",
        exact: true,
      }),
    ).toBeChecked();
    await expect(
      bothCard.getByRole("checkbox", {
        name: "Synthetic Firearms 924",
        exact: true,
      }),
    ).toBeChecked();
    await bothCard.screenshot({
      path: path.join(evidence, "07-admin-two-bank-approval.png"),
    });
    await bothCard
      .getByRole("checkbox", { name: "Synthetic Medical 924", exact: true })
      .uncheck();
    await bothCard.getByRole("button", { name: "Uložiť prístupy" }).click();
    await expect
      .poll(async () =>
        (
          await learners.both.context.request.get(
            base + "/api/questions/" + medical + "-1",
          )
        ).status(),
      )
      .toBe(403);
    await bothCard
      .getByRole("checkbox", { name: "Synthetic Medical 924", exact: true })
      .check();
    await bothCard.getByRole("button", { name: "Uložiť prístupy" }).click();
    await expect
      .poll(async () =>
        (
          await learners.both.context.request.get(
            base + "/api/questions/" + medical + "-1",
          )
        ).status(),
      )
      .toBe(200);
    for (const filename of [
      "source.png",
      "source.jpeg",
      "source.pdf",
      "text.pdf",
    ]) {
      let uploaded;
      if (filename === "source.pdf") {
        await adminPage
          .getByRole("button", { name: "Banky a import", exact: true })
          .click();
        await adminPage
          .getByRole("button", {
            name: "Synthetic Medical 924 · development",
            exact: true,
          })
          .click();
        await adminPage
          .getByLabel("Zdrojové súbory")
          .setInputFiles(path.join(folder, filename));
        await adminPage
          .getByRole("checkbox", {
            name: "Mám oprávnenie spracovať zdroj pomocou AI.",
          })
          .check();
        await adminPage.screenshot({
          path: path.join(evidence, "08-admin-fake-pdf-upload.png"),
          fullPage: true,
        });
        const uploadResponse = adminPage.waitForResponse(
          (r) =>
            r.url().endsWith(`/api/admin/banks/${medical}/imports`) &&
            r.request().method() === "POST",
        );
        await adminPage
          .getByRole("button", { name: "Spustiť import", exact: true })
          .click();
        uploaded = await uploadResponse;
      } else {
        uploaded = await admin.context.request.post(
          `${base}/api/admin/banks/${medical}/imports`,
          {
            headers: admin.headers,
            multipart: {
              authorized: "true",
              files: {
                name: filename,
                mimeType: filename.endsWith("pdf")
                  ? "application/pdf"
                  : filename.endsWith("png")
                    ? "image/png"
                    : "image/jpeg",
                buffer: fs.readFileSync(path.join(folder, filename)),
              },
            },
          },
        );
      }
      expect(uploaded.status()).toBe(200);
      const id = (await uploaded.json()).id;
      await expect
        .poll(
          async () => {
            const j = await (
              await admin.context.request.get(base + "/api/admin/jobs/" + id)
            ).json();
            return j.status;
          },
          { timeout: 150000, intervals: [2000] },
        )
        .toBe("review");
      const j = await (
        await admin.context.request.get(base + "/api/admin/jobs/" + id)
      ).json();
      expect(j.result).toHaveLength(1);
      expect(j.result[0].answer).toContain("H2O");
      expect(j.result[0].body.toLowerCase()).toContain(
        "chemical formula of water",
      );
      expect(j.result[0].body.toLowerCase()).not.toContain("answer:");
      expect(j.result[0].body.toLowerCase()).not.toContain(
        "original synthetic",
      );
      const q = j.result[0];
      manifest.observedSources.push(q.number);
      manifest.routes.push({
        kind: "import",
        provider: j.provider,
        model: j.model,
        input: filename,
      });
      const record = {
        category: q.category,
        number: q.number,
        title: q.title,
        body: q.body,
        answer: q.answer,
        subquestions: q.subquestions || [],
        options: q.options || [],
        source_pages: q.source_pages,
        tags: [],
      };
      expect(
        (
          await admin.context.request.put(
            `${base}/api/admin/jobs/${id}/review`,
            { headers: admin.headers, data: { records: [record] } },
          )
        ).status(),
      ).toBe(200);
      expect(
        (
          await admin.context.request.post(
            `${base}/api/admin/jobs/${id}/apply`,
            { headers: admin.headers },
          )
        ).status(),
      ).toBe(200);
      const installed = await (
        await admin.context.request.get(
          `${base}/api/admin/banks/${medical}/questions`,
        )
      ).json();
      const imported = installed.find((v: any) => v.number === q.number);
      expect(imported.enabled).toBe(false);
      importedIds[q.number] = imported.id;
      manifest.importedRecords.push({
        bankId: medical,
        questionId: imported.id,
        number: q.number,
        input: filename,
      });
    }
    expect(manifest.observedSources.sort()).toEqual([101, 102, 103, 104]);
    await adminPage
      .getByRole("button", { name: "Importy a AI štítky", exact: true })
      .click();
    await adminPage
      .getByRole("button", { name: "Otvoriť návrh", exact: true })
      .first()
      .click();
    await expect(
      adminPage.getByRole("heading", { name: "Kontrola návrhu", exact: true }),
    ).toBeVisible();
    await expect(
      adminPage.getByRole("link", { name: "Zdroj 1 (1 strán)" }),
    ).toBeVisible();
    await adminPage.screenshot({
      path: path.join(evidence, "06-mobile-import-review.png"),
      fullPage: true,
    });
    await adminPage
      .getByRole("button", { name: "Banky a import", exact: true })
      .click();
    await adminPage
      .getByRole("button", {
        name: "Synthetic Medical 924 · development",
        exact: true,
      })
      .click();
    await adminPage
      .getByLabel("Popis / fakulta / skúška")
      .fill(
        "Original synthetic medical bank, reviewed in mobile administration.",
      );
    await adminPage
      .getByRole("button", { name: "Uložiť banku", exact: true })
      .click();
    await expect(adminPage.getByRole("status")).toHaveText("Uložené.");
    const importedRow = adminPage
      .locator(".question-row")
      .filter({ hasText: "biology–101" });
    await importedRow
      .getByRole("button", { name: "Upraviť", exact: true })
      .click();
    await adminPage
      .getByLabel("Názov", { exact: true })
      .last()
      .fill("Imported water reviewed");
    await adminPage.getByRole("checkbox", { name: "Otázka aktívna" }).check();
    await adminPage
      .getByRole("button", { name: "Uložiť otázku", exact: true })
      .click();
    await expect(importedRow).toContainText("aktívna");
    await importedRow
      .getByRole("button", { name: "Upraviť", exact: true })
      .click();
    await adminPage.getByRole("checkbox", { name: "Otázka aktívna" }).uncheck();
    await adminPage
      .getByRole("button", { name: "Uložiť otázku", exact: true })
      .click();
    await expect(importedRow).toContainText("vypnutá");
    await importedRow
      .getByRole("button", { name: "Upraviť", exact: true })
      .click();
    await adminPage.getByRole("checkbox", { name: "Otázka aktívna" }).check();
    await adminPage
      .getByRole("button", { name: "Uložiť otázku", exact: true })
      .click();
    await expect(importedRow).toContainText("aktívna");
    const tag = await admin.context.request.post(
      `${base}/api/admin/banks/${medical}/tagging`,
      {
        headers: admin.headers,
        data: {
          question_ids: [importedIds[101]],
          instruction: "Add topic:water to the water molecule question.",
          rubric:
            "For a question asking the chemical formula of water, use exactly topic:water. This is a synthetic test rubric; no uncertain curriculum classification is needed.",
        },
      },
    );
    const tagid = (await tag.json()).id;
    await expect
      .poll(
        async () =>
          (
            await (
              await admin.context.request.get(base + "/api/admin/jobs/" + tagid)
            ).json()
          ).status,
        { timeout: 150000, intervals: [2000] },
      )
      .toBe("review");
    const tagged = await (
      await admin.context.request.get(base + "/api/admin/jobs/" + tagid)
    ).json();
    expect(tagged.result[0].tags).toContain("topic:water");
    expect(
      (
        await admin.context.request.post(
          `${base}/api/admin/jobs/${tagid}/apply`,
          { headers: admin.headers },
        )
      ).status(),
    ).toBe(200);
    manifest.routes.push({
      kind: "tagging",
      provider: tagged.provider,
      model: tagged.model,
    });
    const learner = learners.medical;
    const page = await learner.context.newPage();
    await page.goto(base);
    await expect(
      page.getByRole("heading", { name: "Synthetic Medical 924", exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: path.join(evidence, "09-user-bank-selection.png"),
      fullPage: true,
    });
    await page
      .getByRole("article")
      .filter({
        has: page.getByRole("heading", {
          name: "Synthetic Medical 924",
          exact: true,
        }),
      })
      .getByRole("button", { name: "Otvoriť banku" })
      .click();
    await page.getByLabel("Štítky", { exact: true }).fill("topic:water");
    await expect(page.locator(".question-row")).toHaveCount(1);
    await page.locator(".question-row input").check();
    await page.getByLabel("Názov výberu").fill("Water learning");
    await page.getByRole("button", { name: "Uložiť výber (1)" }).click();
    await expect(
      page.getByRole("heading", { name: "Water learning" }),
    ).toBeVisible();
    await page.screenshot({
      path: path.join(evidence, "03-mobile-learning-set.png"),
      fullPage: true,
    });
    await page.getByRole("button", { name: "Precvičovať výber" }).click();
    await page.getByRole("button", { name: "Precvičiť túto otázku" }).click();
    await page.getByLabel("Vaša odpoveď").fill("H2O");
    await page.screenshot({
      path: path.join(evidence, "10-user-answer-question.png"),
      fullPage: true,
    });
    const evaluated = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/attempts") && r.request().method() === "POST",
      { timeout: 150000 },
    );
    await page.getByRole("button", { name: "Vyhodnotiť odpoveď" }).click();
    const result = await (await evaluated).json();
    expect(result.status).toBe("completed");
    expect(result.passed).toBe(true);
    await expect(page.getByText(/Celkový výsledok: 100 %/)).toBeVisible();
    expect(result.question_id).toBe(importedIds[101]);
    expect(result.content_snapshot.answer).toContain("H2O");
    manifest.practiceSourceId = result.question_id;
    manifest.routes.push({
      kind: "practice",
      provider: result.provider,
      model: result.model,
    });
    await expect(page.getByText("✓ Úspešná odpoveď")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: path.join(evidence, "04-mobile-evaluated.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.screenshot({
      path: path.join(evidence, "05-desktop-evaluated.png"),
      fullPage: true,
    });
    expect(
      (
        await admin.context.request.put(
          base + "/api/admin/users/" + fixture.users.medical.user_id,
          { headers: admin.headers, data: { approved: true, bank_ids: [] } },
        )
      ).status(),
    ).toBe(200);
    expect(
      (
        await learner.context.request.get(
          base + "/api/questions/" + medical + "-1",
        )
      ).status(),
    ).toBe(403);
    expect(
      await (await learner.context.request.get(base + "/api/history")).json(),
    ).toEqual([]);
    await page.reload();
    await catalogueOnly(page);
    await page.screenshot({
      path: path.join(evidence, "14-access-revoked.png"),
      fullPage: true,
    });
    const loggedOut = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/logout") &&
        response.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Odhlásiť sa", exact: true })
      .click();
    expect((await loggedOut).status()).toBe(200);
    await expect(
      page.getByRole("button", {
        name: "Registrácia / prihlásenie",
        exact: true,
      }),
    ).toBeVisible();
    await catalogueOnly(page);
    await deniedContent(learner.context, 401);
    manifest.accessBoundary.push(
      "revoked and logged out: catalogue only; questions denied again",
    );
    manifest.status = "passed";
    manifest.scenarios = [
      "approved learner selects medical bank",
      "learner answers actual PDF/image-imported question",
      "real model evaluates answer and displays total test result",
      "administrator uploads original fake PDF through browser UI",
      "administrator sees and updates explicit grants for two banks",
    ];
    save();
  } catch (error) {
    manifest.status = "failed";
    manifest.reason =
      "A required real-service assertion failed; inspect sanitized test output.";
    save();
    throw error;
  } finally {
    for (const context of contexts) await context.close();
  }
});
