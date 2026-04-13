export type LogLevel = "INFO" | "WARN" | "ERROR";

type LogContext = Record<string, unknown> | undefined;

const formatPrefix = (level: LogLevel): string => {
  return `[${new Date().toISOString()}] [${level}]`;
};

const safeStringify = (value: unknown): string => {
  try {
    return JSON.stringify(value, (_key, currentValue) => {
      if (currentValue instanceof Error) {
        return {
          name: currentValue.name,
          message: currentValue.message,
          stack: currentValue.stack
        };
      }
      return currentValue;
    });
  } catch {
    return "{\"error\":\"unable_to_stringify_log_context\"}";
  }
};

const formatLine = (level: LogLevel, message: string, context?: LogContext): string => {
  const suffix = context ? ` | ${safeStringify(context)}` : "";
  return `${formatPrefix(level)} ${message}${suffix}`;
};

const write = (level: LogLevel, message: string, context?: LogContext, error?: unknown): void => {
  const line = formatLine(level, message, context);
  if (level === "ERROR") {
    if (typeof error === "undefined") {
      console.error(line);
      return;
    }
    console.error(line, error);
    return;
  }
  if (level === "WARN") {
    console.warn(line);
    return;
  }
  console.info(line);
};

export const consoleLogger = {
  info: (message: string, context?: LogContext): void => {
    write("INFO", message, context);
  },
  warn: (message: string, context?: LogContext): void => {
    write("WARN", message, context);
  },
  error: (message: string, context?: LogContext, error?: unknown): void => {
    write("ERROR", message, context, error);
  }
};
