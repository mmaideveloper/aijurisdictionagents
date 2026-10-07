import React from "react";
import {
  AdminAuthInput, AdminDebugTrace, AdminTraceFilters, AdminTraceSearchPage,
  fetchAdminDebugTrace, fetchAdminTraceSearch
} from "../api/adminModelClient";
import { useLanguage } from "./LanguageProvider";

export default function AdminTraceSearch({ adminAuth, onTrace }: {
  adminAuth: AdminAuthInput;
  onTrace: (trace: AdminDebugTrace | null) => void;
}) {
  const { t } = useLanguage();
  const [filters, setFilters] = React.useState<AdminTraceFilters>({});
  const [page, setPage] = React.useState<AdminTraceSearchPage | null>(null);
  const [submitted, setSubmitted] = React.useState<AdminTraceFilters | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState("");
  const generation = React.useRef(0);
  React.useEffect(() => () => { generation.current += 1; }, []);
  const errorMessage = (reason: unknown) => {
    const status = (reason as { status?: number })?.status;
    return t(status === 401 || status === 403 ? "adminTraceUnauthorized"
      : status === 404 ? "adminTraceExpired" : status === 422 ? "adminTraceInvalid" : "adminTraceUnavailable");
  };
  const search = async (query: AdminTraceFilters, cursor?: string) => {
    const id = ++generation.current;
    setLoading(true);
    setError("");
    onTrace(null);
    try {
      const result = await fetchAdminTraceSearch(adminAuth, query, cursor);
      if (id === generation.current) { setPage(result); setSubmitted(query); }
    } catch (reason) {
      if (id === generation.current) { setPage(null); setError(errorMessage(reason)); }
    } finally { if (id === generation.current) setLoading(false); }
  };
  const select = async (correlationId: string) => {
    const id = ++generation.current;
    setLoading(true);
    setError("");
    onTrace(null);
    try {
      const trace = await fetchAdminDebugTrace(adminAuth, correlationId);
      if (id === generation.current) onTrace(trace);
    } catch (reason) { if (id === generation.current) setError(errorMessage(reason)); }
    finally { if (id === generation.current) setLoading(false); }
  };
  const fields = [
    ["user_id", "adminTraceUserId"], ["case_id", "adminTraceCaseId"],
    ["session_id", "adminTraceSessionId"], ["correlation_id", "adminDebugCorrelationId"]
  ] as const;
  return <div aria-busy={loading}>
    <form className="admin-debug__search" onSubmit={(event) => {
      event.preventDefault();
      if (!fields.some(([key]) => filters[key]?.trim())) { setError(t("adminTraceInvalid")); return; }
      const query = Object.fromEntries(Object.entries(filters).map(([key, value]) => [
        key, key === "start" || key === "end" ? (value ? `${value}Z` : "") : value.trim()
      ]));
      void search(query);
    }}>
      {fields.map(([key, label]) => <label key={key}>{t(label)}<input
        value={filters[key] ?? ""} maxLength={200}
        onChange={(event) => setFilters({ ...filters, [key]: event.target.value })}
      /></label>)}
      <label>{t("adminTraceStart")}<input type="datetime-local" value={filters.start ?? ""}
        onChange={(event) => setFilters({ ...filters, start: event.target.value })} /></label>
      <label>{t("adminTraceEnd")}<input type="datetime-local" value={filters.end ?? ""}
        onChange={(event) => setFilters({ ...filters, end: event.target.value })} /></label>
      <button className="button primary" type="submit" disabled={loading}>{t("adminDebugSearch")}</button>
      <button className="button ghost" type="button" disabled={loading || !filters.correlation_id?.trim()}
        onClick={() => void select(filters.correlation_id!.trim())}>{t("adminTraceExact")}</button>
    </form>
    {loading ? <p role="status">{t("adminTraceLoading")}</p> : null}
    {error ? <p role="alert" className="form-error">{error}</p> : null}
    {page ? <>
      <p role="status">{page.items.length ? t("adminTraceResults") : t("adminTraceEmpty")}</p>
      <div className="admin-table-scroll"><table>
        <thead><tr>{["adminDebugCorrelationId", "adminTraceUserId", "adminTraceCaseId", "adminTraceSessionId", "adminCreated"]
          .map((key) => <th key={key} scope="col">{t(key as Parameters<typeof t>[0])}</th>)}</tr></thead>
        <tbody>{page.items.map((item) => <tr key={`${item.correlation_id}:${item.session_id}`}>
          <td><button type="button" className="button ghost" disabled={loading}
            onClick={() => void select(item.correlation_id)}>{item.correlation_id}</button></td>
          <td>{item.user_id ?? t("adminDebugUnknown")}</td><td>{item.case_id ?? t("adminDebugUnknown")}</td>
          <td>{item.session_id || t("adminDebugUnknown")}</td><td><time>{item.created_at}</time></td>
        </tr>)}</tbody>
      </table></div>
      {page.next_cursor && submitted ? <button className="button ghost" type="button" disabled={loading}
        onClick={() => void search(submitted, page.next_cursor!)}>{t("adminTraceNext")}</button> : null}
    </> : null}
  </div>;
}
