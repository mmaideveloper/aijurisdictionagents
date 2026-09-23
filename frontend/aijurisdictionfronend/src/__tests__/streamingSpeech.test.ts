import { describe, expect, it } from "vitest";
import { TranscriptSegments } from "../audio/streamingSpeech";

describe("streaming transcript", () => {
  it("replaces partials, applies finals once and preserves two utterance lines", () => {
    const draft = new TranscriptSegments();
    draft.update({ type: "partial", segment: 0, text: "Potrebujem" });
    draft.update({ type: "partial", segment: 0, text: "Potrebujem zmluvu" });
    draft.update({ type: "final", segment: 0, text: "Potrebujem zmluvu." });
    draft.update({ type: "partial", segment: 0, text: "stale" });
    draft.update({ type: "final", segment: 0, text: "duplicate" });
    expect(draft.update({ type: "final", segment: 1, text: "Cena je sto eur." }))
      .toBe("Potrebujem zmluvu.\nCena je sto eur.");
  });
});
