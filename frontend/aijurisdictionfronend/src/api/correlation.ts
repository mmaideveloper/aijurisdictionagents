let activeSessionCorrelationId = "";

export const createSessionCorrelationId = (): string => {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `corr-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

export const setActiveSessionCorrelationId = (correlationId: string): void => {
  activeSessionCorrelationId = correlationId.trim();
};

export const correlationHeaders = (correlationId?: string): Record<string, string> => {
  const active = correlationId?.trim() || activeSessionCorrelationId;
  return {
    "x-request-id": createSessionCorrelationId(),
    ...(active ? { "x-correlation-id": active } : {})
  };
};
