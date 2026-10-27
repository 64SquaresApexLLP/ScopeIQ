// Data loader hook: loading / error / data with pull-to-refresh and reload after actions.
// Optional polling: while `keepPolling(data)` is true the data is re-read every `pollMs` (silently, no spinner).
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError } from './api';

export interface PollOptions<T> {
  pollMs: number;
  keepPolling: (data: T) => boolean;
}

type MutatePattern = string | RegExp | ((path: string) => boolean);
type Listener = (pattern?: MutatePattern) => void;
const listeners = new Set<Listener>();

/**
 * Trigger immediate silent re-fetch on all mounted useApi hooks whose paths match pattern.
 * If pattern is omitted, all active useApi hooks are refreshed.
 */
export function mutateApi(pattern?: MutatePattern) {
  for (const fn of Array.from(listeners)) {
    try {
      fn(pattern);
    } catch {}
  }
}

export function useApi<T>(path: string | null, poll?: PollOptions<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(!!path);
  const alive = useRef(true);
  const lastLoadTime = useRef(Date.now());
  const pollRef = useRef(poll);
  pollRef.current = poll;

  const load = useCallback(async (silent: boolean) => {
    if (!path) return;
    if (!silent) setLoading(true);
    try {
      const d = await api.get<T>(path);
      if (alive.current) {
        lastLoadTime.current = Date.now();
        setData(d);
        setError(null);
      }
    } catch (e) {
      if (alive.current) setError(e instanceof ApiError ? e : new ApiError(0, 'CLIENT', String(e)));
    } finally {
      if (alive.current && !silent) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    alive.current = true;
    setData(null);
    void load(false);
    return () => {
      alive.current = false;
    };
  }, [load]);

  // Global cache/invalidation listener: when an endpoint is mutated, silently refresh matching queries
  useEffect(() => {
    if (!path) return;
    const onMutate: Listener = (pattern) => {
      if (!alive.current) return;
      if (!pattern) {
        void load(true);
        return;
      }
      let match = false;
      if (typeof pattern === 'string') {
        match = path === pattern || path.startsWith(pattern) || pattern.startsWith(path);
      } else if (pattern instanceof RegExp) {
        match = pattern.test(path);
      } else if (typeof pattern === 'function') {
        match = pattern(path);
      }
      if (match) {
        void load(true);
      }
    };
    listeners.add(onMutate);
    return () => {
      listeners.delete(onMutate);
    };
  }, [path, load]);

  // Web window focus refresh (throttled to at least 4s)
  useEffect(() => {
    if (typeof window !== 'undefined' && window.addEventListener) {
      const onWindowFocus = () => {
        if (alive.current && path && Date.now() - lastLoadTime.current > 4000) {
          void load(true);
        }
      };
      window.addEventListener('focus', onWindowFocus);
      return () => {
        window.removeEventListener('focus', onWindowFocus);
      };
    }
  }, [path, load]);

  // polling: re-arm after every successful read while the caller says the data is still changing
  useEffect(() => {
    const p = pollRef.current;
    if (!p || data == null || !p.keepPolling(data)) return;
    const t = setTimeout(() => void load(true), p.pollMs);
    return () => clearTimeout(t);
  }, [data, load]);

  const reload = useCallback((silent = false) => load(silent), [load]);
  return { data, error, loading, reload };
}

