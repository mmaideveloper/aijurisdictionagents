import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const scenarioUrl = new URL("../cases/audio-payment-confirmation.json", import.meta.url);
const scenario = JSON.parse(await readFile(scenarioUrl, "utf8"));

assert.equal(scenario.locale, "sk-SK");
assert.equal(scenario.syntheticOnly, true);
assert.match(scenario.audioFixture, /\.wav$/);
assert.ok(scenario.expectedNormalizedTranscript.includes("5000 eur"));
assert.deepEqual(
  {
    type: scenario.document.type,
    amount: scenario.document.amount,
    recipient: scenario.document.recipient,
    address: scenario.document.address,
    humanReview: scenario.document.requiresHumanReview
  },
  {
    type: "Potvrdenie o zaplatení",
    amount: "5000 EUR",
    recipient: "Janko Hraško",
    address: "Testovo 10",
    humanReview: true
  }
);
assert.ok(scenario.retentionDays > 0 && scenario.retentionDays <= 7);

for (const evidence of ["03-document-preview.png", "04-payment-confirmation.pdf", "05-pdf-first-page.png"]) {
  assert.ok(scenario.requiredEvidence.includes(evidence), `${evidence} is required`);
}
for (const forbidden of ["password", "verification_code", "device_auth_token", "raw_audio"]) {
  assert.ok(scenario.forbiddenEvidenceFields.includes(forbidden), `${forbidden} must be forbidden`);
}

console.log(`Validated E2E evidence contract: ${scenario.id}`);
