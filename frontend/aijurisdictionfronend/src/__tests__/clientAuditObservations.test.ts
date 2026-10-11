import { afterEach, expect, it, vi } from "vitest";
import { streamSession } from "../api/chatClient";

afterEach(() => { vi.unstubAllGlobals(); });

it("reports only transport metadata and keeps the stream request identity", async () => {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    if (url.endsWith("/client-observations")) return new Response(null, { status: 202 });
    return new Response(new ReadableStream({ start(controller) { controller.close(); } }), { status: 200 });
  }));
  for await (const event of streamSession({ sessionId: "synthetic", correlationId: "correlation", instruction: "PRIVATE INPUT", userId: "owner", deviceId: "device", deviceAuthToken: "synthetic-token" })) void event;
  const reports = calls.filter(call => call.url.endsWith("/client-observations"));
  expect(reports.map(call => JSON.parse(String(call.init.body)).phase)).toEqual(["dispatch", "headers_received", "stream_completed"]);
  const requestId = (calls[0]!.init.headers as Record<string, string>)["x-request-id"];
  for (const report of reports) {
    expect(JSON.parse(String(report.init.body)).request_id).toBe(requestId);
    expect(report.init.body).not.toContain("PRIVATE INPUT");
    expect(report.init.body).not.toContain("synthetic-token");
  }
});

it("does not fail the chat when optional observation delivery fails", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    if (url.endsWith("/client-observations")) throw new Error("offline");
    return new Response(new ReadableStream({ start(controller) { controller.close(); } }), { status: 200 });
  }));
  for await (const event of streamSession({ sessionId: "synthetic", correlationId: "correlation", instruction: "synthetic", userId: "owner", deviceId: "device", deviceAuthToken: "synthetic-token" })) void event;
});
