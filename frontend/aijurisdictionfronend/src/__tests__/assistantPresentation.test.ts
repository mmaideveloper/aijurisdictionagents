// @vitest-environment jsdom

import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  AI_ORCHESTRATOR_AGENT_LABEL,
  assistantAgentDisplayName,
  decodeNumericCharacterReferences,
  normalizeAssistantPresentationText
} from "../utils/assistantPresentation";

describe("assistant presentation normalization", () => {
  it("decodes decimal and hexadecimal character references as plain React text", () => {
    expect(decodeNumericCharacterReferences("Balík dokumentov&#x20;je pripravený&#32;na stiahnutie."))
      .toBe("Balík dokumentov je pripravený na stiahnutie.");
  });

  it("keeps invalid Unicode references visible instead of producing malformed text", () => {
    expect(decodeNumericCharacterReferences("invalid: &#x110000; &#xD800;"))
      .toBe("invalid: &#x110000; &#xD800;");
  });

  it("keeps decoded markup inert because the normalized value is still rendered as React text", () => {
    render(React.createElement("p", { "data-testid": "safe-text" }, normalizeAssistantPresentationText(
      "&#x3c;script&#x3e;alert(1)&#x3c;/script&#x3e;"
    )));

    expect(screen.getByTestId("safe-text").textContent).toBe("<script>alert(1)</script>");
    expect(document.querySelector("script")).toBeNull();
    cleanup();
  });

  it("uses the product label in visible messages while leaving other framework words unchanged", () => {
    expect(normalizeAssistantPresentationText("LangGraph selected the safe conversation path."))
      .toBe(`${AI_ORCHESTRATOR_AGENT_LABEL} selected the safe conversation path.`);
    expect(normalizeAssistantPresentationText("LangGraphical routing stays unchanged."))
      .toBe("LangGraphical routing stays unchanged.");
  });

  it("maps internal orchestrator agent identifiers without changing audit-friendly names elsewhere", () => {
    expect(assistantAgentDisplayName("LangGraphPrimaryRouter", "AI Assistant"))
      .toBe(AI_ORCHESTRATOR_AGENT_LABEL);
    expect(assistantAgentDisplayName("LawyerSlovakia", "AI Assistant"))
      .toBe("LawyerSlovakia");
    expect(assistantAgentDisplayName(null, "AI Assistant"))
      .toBe("AI Assistant");
  });
});
