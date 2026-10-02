import React from "react";
import { fetchLatestCaseCorrelationId } from "../api/caseClient";
import { setActiveSessionCorrelationId } from "../api/correlation";

/** The history-keyed thread may remount; its diagnostic reference belongs to the workspace. */
export const useCaseCorrelationId = (userId?: string, caseId?: string) => {
  const scope = JSON.stringify([userId ?? "", caseId ?? ""]);
  const selection = React.useMemo(() => ({ scope }), [scope]);
  const activeSelection = React.useRef(selection);
  activeSelection.current = selection;
  const [reference, setReference] = React.useState({ scope, id: "" });
  const correlationId = reference.scope === scope ? reference.id : "";

  const setCorrelationId = React.useCallback((id: string) => {
    // A session creation request from the previous case may finish after navigation.
    if (activeSelection.current === selection) setReference({ scope, id: id.trim() });
  }, [scope, selection]);

  React.useEffect(() => {
    let current = true;
    const controller = new AbortController();
    setReference({ scope, id: "" });
    if (userId && caseId) {
      void fetchLatestCaseCorrelationId(caseId, userId, controller.signal)
        .then((id) => {
          if (current) {
            // A newly started chat takes precedence over a slower historical lookup.
            setReference((previous) => previous.scope === scope && previous.id
              ? previous : { scope, id });
          }
        })
        .catch(() => {
          // Diagnostics must not prevent chat when history is unavailable.
        });
    }
    return () => {
      current = false;
      controller.abort();
    };
  }, [caseId, scope, userId]);

  React.useEffect(() => {
    setActiveSessionCorrelationId(correlationId);
    return () => setActiveSessionCorrelationId("");
  }, [correlationId, scope]);

  return { correlationId, setCorrelationId };
};
