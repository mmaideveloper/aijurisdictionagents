// @vitest-environment jsdom
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AdminTraceSearch from "../components/AdminTraceSearch";
import { AdminDebugTrace, AdminTraceSearchPage, fetchAdminDebugTrace, fetchAdminTraceSearch } from "../api/adminModelClient";

vi.mock("../components/LanguageProvider", () => ({ useLanguage: () => ({ t: (key: string) => key }) }));
vi.mock("../api/adminModelClient", () => ({ fetchAdminTraceSearch: vi.fn(), fetchAdminDebugTrace: vi.fn() }));
const result: AdminTraceSearchPage = {
  items: [{ correlation_id: "corr-a", session_id: "session-a", user_id: "user-a", case_id: "case-a",
    created_at: "2026-10-07T08:00:00Z", expires_at: "2026-10-14T08:00:00Z" }],
  next_cursor: "page-2", start: "2026-10-01T08:00:00Z", end: "2026-10-07T08:00:00Z", limit: 25, retention_days: 7
};
afterEach(() => { cleanup(); vi.resetAllMocks(); });
describe("metadata trace search", () => {
  it("combines identifiers, preserves submitted pagination filters and opens a selected trace", async () => {
    const user = userEvent.setup();
    const onTrace = vi.fn();
    vi.mocked(fetchAdminTraceSearch).mockResolvedValue(result);
    vi.mocked(fetchAdminDebugTrace).mockResolvedValue({ correlation_id: "corr-a" } as AdminDebugTrace);
    render(<AdminTraceSearch adminAuth="admin" onTrace={onTrace} />);
    await user.type(screen.getByLabelText("adminTraceUserId"), "user-a");
    await user.type(screen.getByLabelText("adminTraceCaseId"), "case-a");
    await user.click(screen.getByRole("button", { name: "adminDebugSearch" }));
    await screen.findByRole("button", { name: "corr-a" });
    expect(fetchAdminTraceSearch).toHaveBeenCalledWith("admin", { user_id: "user-a", case_id: "case-a" }, undefined);
    await user.clear(screen.getByLabelText("adminTraceCaseId"));
    await user.type(screen.getByLabelText("adminTraceCaseId"), "case-b");
    await user.click(screen.getByRole("button", { name: "adminTraceNext" }));
    await waitFor(() => expect(fetchAdminTraceSearch).toHaveBeenLastCalledWith("admin", { user_id: "user-a", case_id: "case-a" }, "page-2"));
    await user.click(screen.getByRole("button", { name: "corr-a" }));
    await waitFor(() => expect(onTrace).toHaveBeenLastCalledWith({ correlation_id: "corr-a" }));
  });
  it("shows an empty state and unknown historical ownership", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAdminTraceSearch).mockResolvedValueOnce({ ...result, items: [], next_cursor: null })
      .mockResolvedValueOnce({ ...result, items: [{ ...result.items[0]!, user_id: null, case_id: null }] });
    render(<AdminTraceSearch adminAuth="admin" onTrace={vi.fn()} />);
    await user.type(screen.getByLabelText("adminTraceSessionId"), "session-a");
    await user.click(screen.getByRole("button", { name: "adminDebugSearch" }));
    expect(await screen.findByText("adminTraceEmpty")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "adminDebugSearch" }));
    await waitFor(() => expect(screen.getAllByText("adminDebugUnknown")).toHaveLength(2));
  });
  it.each([[403, "adminTraceUnauthorized"], [503, "adminTraceUnavailable"], [422, "adminTraceInvalid"]])(
    "localizes search error %s", async (status, message) => {
      const user = userEvent.setup();
      vi.mocked(fetchAdminTraceSearch).mockRejectedValue(Object.assign(new Error("sensitive server detail"), { status }));
      render(<AdminTraceSearch adminAuth="admin" onTrace={vi.fn()} />);
      await user.type(screen.getByLabelText("adminTraceUserId"), "user-a");
      await user.click(screen.getByRole("button", { name: "adminDebugSearch" }));
      expect((await screen.findByRole("alert")).textContent).toBe(message);
    }
  );
  it("requires an identifier and reports expired exact lookups", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAdminDebugTrace).mockRejectedValue(Object.assign(new Error("expired"), { status: 404 }));
    render(<AdminTraceSearch adminAuth="admin" onTrace={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "adminDebugSearch" }));
    expect(fetchAdminTraceSearch).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText("adminDebugCorrelationId"), "corr-old");
    await user.click(screen.getByRole("button", { name: "adminTraceExact" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("adminTraceExpired"));
  });
});
