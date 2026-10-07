// Reusable logger. Console output from settings.logLevel; warnings/errors at or above settings.remoteLogLevel
// are forwarded to the API (POST /logs/client) so they land in AUDIT.APP_LOG with the user's correlation id.
import { LogLevel, settings } from './config';

const ORDER: Record<LogLevel, number> = { debug: 10, info: 20, warn: 30, error: 40 };
type Sink = (level: LogLevel, message: string, context?: Record<string, unknown>) => void;
let remoteSink: Sink | null = null;

export function setRemoteSink(sink: Sink | null) {
  remoteSink = sink;
}

function emit(level: LogLevel, scope: string, message: string, context?: Record<string, unknown>) {
  const line = `[${new Date().toISOString()}] ${level.toUpperCase()} ${scope}: ${message}`;
  if (ORDER[level] >= ORDER[settings.logLevel]) {
    const fn = level === 'error' ? console.error : level === 'warn' ? console.warn : console.log;
    context ? fn(line, context) : fn(line);
  }
  if (remoteSink && ORDER[level] >= ORDER[settings.remoteLogLevel]) {
    try {
      remoteSink(level, `${scope}: ${message}`, { ...context, env: settings.env });
    } catch {
      /* never let logging break the app */
    }
  }
}

export function getLogger(scope: string) {
  return {
    debug: (m: string, c?: Record<string, unknown>) => emit('debug', scope, m, c),
    info: (m: string, c?: Record<string, unknown>) => emit('info', scope, m, c),
    warn: (m: string, c?: Record<string, unknown>) => emit('warn', scope, m, c),
    error: (m: string, c?: Record<string, unknown>) => emit('error', scope, m, c),
  };
}
