// Data loader hook: loading / error / data with pull-to-refresh and reload after actions.
// Optional polling: while `keepPolling(data)` is true the data is re-read every `pollMs` (silently, no spinner).
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError } from './api';

export interface PollOptions<T> {
  pollMs: number;
  keepPolling: (data: T) => boolean;
}

export function useApi<T>(path: string | null, poll?: PollOptions<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(!!path);
  const alive = useRef(true);
  const pollRef = useRef(poll);
  pollRef.current = poll;

  const load = useCallback(async (silent: boolean) => {
    if (!path) return;
    if (!silent) setLoading(true);
    try {
      const d = await api.get<T>(path);
      if (alive.current) {
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

  // polling: re-arm after every successful read while the caller says the data is still changing
  useEffect(() => {
    const p = pollRef.current;
    if (!p || data == null || !p.keepPolling(data)) return;
    const t = setTimeout(() => void load(true), p.pollMs);
    return () => clearTimeout(t);
  }, [data, load]);

  const reload = useCallback(() => load(false), [load]);
  return { data, error, loading, reload };
}
