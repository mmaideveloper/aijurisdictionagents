// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SoftwareAssessment } from "../components/SoftwareAssessment";

const activeCase = { id: "synthetic-case", documents: [{ id: "synthetic-doc", kind: "uploaded", originalFilename: "supplier.pdf" }] };
vi.mock("../state/CaseProvider", () => ({ useCases: () => ({ activeCase, uploadDocumentsToCase: vi.fn() }) }));
vi.mock("../auth/webAuth", () => ({ useAuth: () => ({ user: { userId: "synthetic-user", deviceId: "synthetic-device", deviceAuthToken: "synthetic-test-only-token" } }) }));
vi.mock("../api/chatClient", () => ({ chatApiRuntimeConfig: () => ({ baseUrl: "http://localhost", apiKey: "synthetic" }), parseApiErrorResponse: async () => ({ message: "Assessment evidence failed validation" }) }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("Software assessment", () => {
  it("does not add hidden upload controls to the normal chat flow", () => {
    render(<SoftwareAssessment />);
    expect(document.querySelector('input[type="file"]')).toBeNull();
  });
  it("sends unknown facts, explicit document selection and device authorization", async () => {
    const result = { assessment_id: "a1", revision: 1, warning: "Expert review required", provider: "not_called", model: "not_called", coverage: ["Legal coverage missing"], documents: [], sources: [], drafts: [],
      output: { summary: "More facts required", questions: ["What is the intended purpose?"], actions: [], applicability: [], supplier_checklist: [], verification_plan: [], recommended_documents: [], architecture_recommendations: [], responsibilities: [], release_blockers: [] } };
    const fetch = vi.fn().mockImplementation(async (_url: string, init: RequestInit) =>
      new Response(JSON.stringify(init.method === "POST" ? result : { items: [] })));
    vi.stubGlobal("fetch", fetch);
    render(<SoftwareAssessment selectedModelProfileId="chosen-model" />);
    const details = document.querySelector("details")!;
    // jsdom does not emulate native summary toggling.
    details.open = true; fireEvent(details, new Event("toggle"));
    fireEvent.change(await screen.findByLabelText("description"), { target: { value: "Synthetic unspecified software" } });
    fireEvent.click(screen.getByLabelText("supplier.pdf"));
    fireEvent.click(screen.getByText("Assess / reassess software"));
    await screen.findByText("Question: What is the intended purpose?");
    const call = fetch.mock.calls.find(item => item[1]?.method === "POST")!;
    const body = JSON.parse(call[1].body);
    expect(body.document_ids).toEqual(["synthetic-doc"]);
    expect(body.facts.uses_ai).toBeNull();
    expect(body.external_acknowledged).toBe(false);
    expect(body.selected_model_profile_id).toBe("chosen-model");
    expect(call[1].headers["x-jurisdigta-device-id"]).toBe("synthetic-device");
    expect(screen.getByText("No grounded actions yet. This does not establish compliance.")).toBeTruthy();
  });
});
