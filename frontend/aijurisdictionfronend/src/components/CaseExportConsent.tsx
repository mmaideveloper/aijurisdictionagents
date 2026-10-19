import React, { useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/webAuth";
import { chatApiRuntimeConfig } from "../api/chatClient";

type ExportItem = { request_id: string; admin_id: string; admin_name: string; admin_email: string; purpose: string; expires_at: string; status: string; cases: { case_id: string; decision: string }[] };

export function CaseExportConsent({ admin = false }: { admin?: boolean }) {
  const { user } = useAuth();
  const currentIdentity = useRef(user?.userId);
  currentIdentity.current = user?.userId;
  const [items, setItems] = useState<ExportItem[]>([]);
  const [caseIds, setCaseIds] = useState("");
  const [purpose, setPurpose] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const config = chatApiRuntimeConfig();
  const base = `${config.baseUrl}/v1/case-exports`;
  const headers = { "content-type": "application/json", "x-api-key": config.apiKey ?? "", "x-jurisdigta-user-id": user?.userId ?? "", "x-jurisdigta-device-id": user?.deviceId ?? "", "x-jurisdigta-device-token": user?.deviceAuthToken ?? "" };
  const load = async () => {
    const response = await fetch(`${base}?admin=${admin}`, { headers, cache: "no-store" });
    if (!response.ok) throw new Error("Export requests unavailable. Sign in with the required permission.");
    const nextItems = await response.json();
    if (currentIdentity.current === user?.userId) setItems(nextItems);
  };
  useEffect(() => {
    setItems([]); setError("");
    if (!user) return;
    let live = true;
    const refresh = () => { if (live) void load().catch(e => { if (live) setError(String(e.message)); }); };
    refresh();
    const timer = setInterval(refresh, 15000);
    return () => { live = false; clearInterval(timer); };
    // Reload when the authenticated identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.userId, user?.deviceAuthToken, admin]);

  const act = async (suffix: string, body?: object) => {
    setBusy(true); setError("");
    try {
      const response = await fetch(base + suffix, { method: "POST", headers, body: body ? JSON.stringify(body) : undefined, cache: "no-store" });
      if (!response.ok) throw new Error("Action denied or unavailable. Refresh the request before trying again.");
      if (suffix.endsWith("/download")) {
        const url = URL.createObjectURL(await response.blob());
        const link = document.createElement("a"); link.href = url; link.download = "consented-case-export.zip"; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Export action failed"); }
    finally { setBusy(false); }
  };
  return <section aria-label="Case export consent">
    <h2>{admin ? "Request consented case export" : "Case export requests"}</h2>
    <p>Case content is encrypted in storage. The service decrypts it for authorized AI processing.</p>
    <p>Approving lets the named administrator download all documents, messages, metadata and citations for the listed cases once. Consent expires after 24 hours. Prepared archives expire after one hour. You can revoke before download; downloaded copies cannot be recalled.</p>
    {admin && <form onSubmit={e => { e.preventDefault(); void act("", { case_ids: caseIds.split(/[\s,]+/).filter(Boolean), purpose }); }}>
      <label>Selected case IDs <textarea value={caseIds} onChange={e => setCaseIds(e.target.value)} required /></label>
      <label>Purpose <input value={purpose} onChange={e => setPurpose(e.target.value)} minLength={3} maxLength={500} required /></label>
      <button disabled={busy} type="submit">Request owner consent</button>
    </form>}
    {error && <p role="alert">{error}</p>}
    <button disabled={busy} onClick={() => void load().catch(e => setError(e.message))}>Refresh export requests</button>
    {!items.length && <p>No export requests.</p>}
    {items.map(item => <article key={item.request_id} data-testid="case-export-request">
      <p>Request: {item.request_id}</p><p>Administrator: {item.admin_name} ({item.admin_email}) · {item.admin_id}</p><p>Purpose: {item.purpose}</p>
      <p>Status: <strong>{item.status}</strong> · Consent expires: {item.expires_at}</p>
      <ul>{item.cases.map(c => <li key={c.case_id}>{c.case_id}: {c.decision}</li>)}</ul>
      {!admin && item.status === "pending" && item.cases.every(c => c.decision === "pending") && <>
        <button disabled={busy} onClick={() => void act(`/${item.request_id}/decision`, { decision: "approved" })}>Approve this export</button>
        <button disabled={busy} onClick={() => void act(`/${item.request_id}/decision`, { decision: "denied" })}>Deny this export</button>
      </>}
      {!admin && ["pending", "ready"].includes(item.status) && item.cases.some(c => c.decision === "approved") && <button disabled={busy} onClick={() => void act(`/${item.request_id}/decision`, { decision: "revoked" })}>Revoke consent</button>}
      {admin && item.status === "ready" && <button disabled={busy} onClick={() => void act(`/${item.request_id}/download`)}>Download once</button>}
    </article>)}
  </section>;
}
