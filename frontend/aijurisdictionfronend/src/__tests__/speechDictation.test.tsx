// @vitest-environment jsdom
import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SpeechDictation } from "../components/SpeechDictation";
import { fetchSpeechRoute, startStreamingSpeech } from "../audio/streamingSpeech";
import type { SpeechEvent } from "../audio/streamingSpeech";

vi.mock("../auth/webAuth", () => ({ useAuth: () => ({ user: { userId: "synthetic", deviceId: "device", deviceAuthToken: "test" } }) }));
vi.mock("../components/LanguageProvider", () => ({ useLanguage: () => ({ language: "sk", t: (key: string) => key }) }));
vi.mock("../audio/streamingSpeech", async (original) => ({
  ...await original<typeof import("../audio/streamingSpeech")>(), fetchSpeechRoute: vi.fn(), startStreamingSpeech: vi.fn(),
}));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("speech review", () => {
  it("requires consent, displays two live lines and releases only the final reviewed draft", async () => {
    vi.mocked(fetchSpeechRoute).mockResolvedValue({ provider: "Azure Speech", model: "speech", region: "westeurope", external: true,
      model_profile_id: "speech", route_revision: "revision", max_seconds: 120, locales: ["sk-SK"], profiles: [] });
    let emit: (event: SpeechEvent) => void = () => undefined;
    const cancel = vi.fn();
    vi.mocked(startStreamingSpeech).mockImplementation((options) => { emit = options.onEvent; return { stop: vi.fn(), cancel }; });
    const onFinal = vi.fn();
    const { unmount } = render(<SpeechDictation caseId="case" onFinal={onFinal} onBusy={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "sttDictate" }));
    await screen.findByRole("button", { name: "sttConsentStart" });
    expect(startStreamingSpeech).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "sttConsentStart" }));
    act(() => {
      emit({ type: "ready" });
      emit({ type: "final", segment: 0, text: "Potrebujem kúpnu zmluvu." });
      emit({ type: "partial", segment: 1, text: "Cena je sto eur." });
    });
    expect(screen.getByTestId("speech-live-transcript").textContent).toBe("Potrebujem kúpnu zmluvu.\nCena je sto eur.");
    expect(onFinal).not.toHaveBeenCalled();
    act(() => { emit({ type: "final", segment: 1, text: "Cena je sto eur." }); emit({ type: "done" }); });
    expect(onFinal).toHaveBeenCalledWith("Potrebujem kúpnu zmluvu.\nCena je sto eur.");
    expect(onFinal).toHaveBeenCalledTimes(1);
    unmount();
    act(() => emit({ type: "done" }));
    expect(onFinal).toHaveBeenCalledTimes(1);
  });

  it("cancels capture and ignores late results on case navigation", async () => {
    vi.mocked(fetchSpeechRoute).mockResolvedValue({ provider: "Azure Speech", model: "speech", region: "westeurope", external: true,
      model_profile_id: "speech", route_revision: "revision", max_seconds: 120, locales: ["sk-SK"], profiles: [] });
    let emit: (event: SpeechEvent) => void = () => undefined;
    const cancel = vi.fn();
    vi.mocked(startStreamingSpeech).mockImplementation((options) => { emit = options.onEvent; return { stop: vi.fn(), cancel }; });
    const onFinal = vi.fn(); const onBusy = vi.fn();
    const view = render(<SpeechDictation caseId="one" onFinal={onFinal} onBusy={onBusy} />);
    fireEvent.click(screen.getByRole("button", { name: "sttDictate" }));
    fireEvent.click(await screen.findByRole("button", { name: "sttConsentStart" }));
    act(() => emit({ type: "ready" }));
    view.rerender(<SpeechDictation caseId="two" onFinal={onFinal} onBusy={onBusy} />);
    act(() => emit({ type: "done" }));
    await waitFor(() => expect(cancel).toHaveBeenCalled());
    expect(onFinal).not.toHaveBeenCalled();
  });
});
