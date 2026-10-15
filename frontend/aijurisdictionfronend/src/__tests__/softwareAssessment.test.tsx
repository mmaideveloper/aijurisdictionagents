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
  it("uses the distinct IT contract, preserves country and only recommends documentation", async () => {
    const result = { assessment_id: "it1", revision: 1, warning: "Review required", provider: "not_called", model: "not_called", coverage: [], documents: [], sources: [], drafts: [],
      output: { summary: "Jurisdikcia mimo rozsahu SK + EU: CZ", questions: ["Czech national-law review required"], actions: [], applicability: [], supplier_checklist: [], verification_plan: [], recommended_documents: ["Purpose map"], architecture_recommendations: [], responsibilities: [], release_blockers: [] } };
    const fetch = vi.fn().mockImplementation(async (_url: string, init: RequestInit) => new Response(JSON.stringify(init.method === "POST" ? result : { items: [] })));
    vi.stubGlobal("fetch", fetch);
    render(<SoftwareAssessment organizationalIT />);
    const details = document.querySelector("details")!;
    details.open = true; fireEvent(details, new Event("toggle"));
    fireEvent.change(await screen.findByLabelText("description"), { target: { value: "Synthetic Czech ZdravieHospital warehouse" } });
    fireEvent.change(screen.getByLabelText(/Krajiny/), { target: { value: "CZ" } });
    fireEvent.click(screen.getByText("Posúdiť / doplniť právnu analýzu IT"));
    await screen.findByText("Jurisdikcia mimo rozsahu SK + EU: CZ");
    const call = fetch.mock.calls.find(item => item[1]?.method === "POST")!;
    expect(call[0]).toContain("/it-assessments");
    expect(JSON.parse(call[1].body).facts.it_context.countries).toEqual(["CZ"]);
    expect(screen.getByText("Purpose map")).toBeTruthy();
    expect(screen.queryByText("Draft Purpose map")).toBeNull();
    expect(screen.queryByText("Download assessment and drafts PDF")).toBeNull();
  });
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
