import { describe, expect, it } from "vitest";
import { normalizePresentationBlock } from "../presentation";

const validBlock = {
  schema_version: 1,
  renderer_id: "sanitized_json",
  renderer_version: 1,
  data: { answer: "Safe" },
  fallback_text: "Safe",
  citations: [],
  notices: ["Human review required"],
  selection: {
    policy_id: "test.v1",
    reason_code: "explicit_user_format",
    explicit_user_request: true,
    model_proposal_accepted: false
  }
};

describe("presentation contract", () => {
  it("accepts a bounded supported presentation block", () => {
    expect(normalizePresentationBlock(validBlock)?.renderer_id).toBe("sanitized_json");
  });

  it("rejects executable or unknown renderer identifiers", () => {
    expect(normalizePresentationBlock({ ...validBlock, renderer_id: "html" })).toBeNull();
  });

  it("rejects unsupported schema versions and oversized fallback text", () => {
    expect(normalizePresentationBlock({ ...validBlock, schema_version: 2 })).toBeNull();
    expect(normalizePresentationBlock({ ...validBlock, fallback_text: "x".repeat(12_001) })).toBeNull();
  });
});
