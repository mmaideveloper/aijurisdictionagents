// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchLatestCaseCorrelationId } from "../api/caseClient";
import { correlationHeaders } from "../api/correlation";
import { useCaseCorrelationId } from "../pages/useCaseCorrelationId";

vi.mock("../api/caseClient", () => ({ fetchLatestCaseCorrelationId: vi.fn() }));
const lookup = vi.mocked(fetchLatestCaseCorrelationId);
const deferred = () => {
  let resolve!: (id: string) => void;
  const promise = new Promise<string>((done) => { resolve = done; });
  return { promise, resolve };
};

describe("case diagnostic reference", () => {
  beforeEach(() => { lookup.mockReset().mockResolvedValue(""); });
  afterEach(cleanup);

  it("restores a saved reference on reopening without sending a message", async () => {
    lookup.mockResolvedValue("saved-reference");
    const first = renderHook(() => useCaseCorrelationId("user-a", "case-a"));
    await waitFor(() => expect(first.result.current.correlationId).toBe("saved-reference"));
    first.unmount();
    expect(correlationHeaders()["x-correlation-id"]).toBeUndefined();
    const reopened = renderHook(() => useCaseCorrelationId("user-a", "case-a"));
    await waitFor(() => expect(reopened.result.current.correlationId).toBe("saved-reference"));
    expect(lookup).toHaveBeenCalledTimes(2);
  });

  it("keeps a live ID when a slower saved-reference lookup finishes", async () => {
    const pending = deferred();
    lookup.mockReturnValue(pending.promise);
    const { result } = renderHook(() => useCaseCorrelationId("user-a", "case-a"));
    act(() => result.current.setCorrelationId("live-reference"));
    await act(async () => pending.resolve("older-reference"));
    expect(result.current.correlationId).toBe("live-reference");
    expect(correlationHeaders()["x-correlation-id"]).toBe("live-reference");
  });

  it("ignores late lookups and live callbacks from a previous case or user", async () => {
    const pending = deferred();
    lookup.mockReturnValueOnce(pending.promise);
    const { result, rerender } = renderHook(
      ({ user, caseId }) => useCaseCorrelationId(user, caseId),
      { initialProps: { user: "user-a", caseId: "case-a" } }
    );
    const oldCallback = result.current.setCorrelationId;
    act(() => oldCallback("case-a-reference"));
    rerender({ user: "user-a", caseId: "case-b" });
    expect(result.current.correlationId).toBe("");
    await act(async () => pending.resolve("late-case-a"));
    act(() => oldCallback("late-live-case-a"));
    expect(result.current.correlationId).toBe("");
    act(() => result.current.setCorrelationId("case-b-reference"));
    rerender({ user: "user-b", caseId: "case-b" });
    await act(async () => {});
    expect(result.current.correlationId).toBe("");
    expect(correlationHeaders()["x-correlation-id"]).toBeUndefined();
    rerender({ user: "user-a", caseId: "case-a" });
    await act(async () => {});
    act(() => oldCallback("late-reference-from-first-visit"));
    expect(result.current.correlationId).toBe("");
  });

  it("does not look up guest sessions and keeps chat usable on lookup failure", async () => {
    const guest = renderHook(() => useCaseCorrelationId());
    expect(lookup).not.toHaveBeenCalled();
    act(() => guest.result.current.setCorrelationId("guest-reference"));
    expect(guest.result.current.correlationId).toBe("guest-reference");
    guest.unmount();
    lookup.mockRejectedValue(new Error("offline"));
    const { result } = renderHook(() => useCaseCorrelationId("user-a", "case-a"));
    await act(async () => {});
    expect(result.current.correlationId).toBe("");
    act(() => result.current.setCorrelationId("new-reference"));
    expect(result.current.correlationId).toBe("new-reference");
  });
});
