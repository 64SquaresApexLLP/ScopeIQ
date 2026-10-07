// API client: bearer token, correlation id per request, one error type (ApiError) carrying the server's
// error envelope {code, message, correlation_id, details}.
import { settings } from './config';
import { getLogger, setRemoteSink } from './logger';

const log = getLogger('api');
let token: string | null = null;
let onUnauthorized: (() => void) | null = null;

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public correlationId?: string, public details?: unknown) {
    super(message);
  }
}

export function setToken(t: string | null) {
  token = t;
}
export const authedUrl = (path: string) => `${settings.apiUrl}${path}${path.includes('?') ? '&' : '?'}access_token=${encodeURIComponent(token ?? '')}`;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

const newId = () => Math.random().toString(16).slice(2, 10) + Date.now().toString(16).slice(-8);

export async function request<T>(method: string, path: string, body?: unknown, form?: FormData): Promise<T> {
  const cid = newId();
  const headers: Record<string, string> = { 'X-Correlation-ID': cid };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const t0 = Date.now();
  let res: Response;
  try {
    res = await fetch(settings.apiUrl + path, { method, headers, body: form ?? (body !== undefined ? JSON.stringify(body) : undefined) });
  } catch (e) {
    if (path !== '/logs/client') log.warn(`network error on ${method} ${path}`, { error: String(e) });
    throw new ApiError(0, 'NETWORK', `Cannot reach the ScopeIQ API at ${settings.apiUrl}. Is the server running?`, cid);
  }
  if (settings.logNetwork) log.debug(`${method} ${path} -> ${res.status} (${Date.now() - t0} ms)`, { cid });
  if (res.status === 401 && onUnauthorized) onUnauthorized();
  const ct = res.headers.get('content-type') || '';
  const data = ct.includes('application/json') ? await res.json() : await res.text();
  if (!res.ok) {
    const e = (data && typeof data === 'object' && 'error' in data ? (data as any).error : {}) as any;
    throw new ApiError(res.status, e.code ?? `HTTP-${res.status}`, e.message ?? String(data).slice(0, 200), e.correlation_id ?? cid, e.details);
  }
  return data as T;
}

export const api = {
  get: <T>(p: string) => request<T>('GET', p),
  post: <T>(p: string, b?: unknown) => request<T>('POST', p, b ?? {}),
  patch: <T>(p: string, b: unknown) => request<T>('PATCH', p, b),
  del: <T>(p: string) => request<T>('DELETE', p),
  upload: <T>(p: string, form: FormData) => request<T>('POST', p, undefined, form),
  fileUrl: (rel: string) => `${settings.apiUrl}${rel.startsWith('/') ? rel : '/' + rel}`,
};

// forward client warnings/errors to the server once signed in
setRemoteSink((level, message, context) => {
  if (!token) return;
  request('POST', '/logs/client', { level, message: message.slice(0, 3900), context }).catch(() => undefined);
});
