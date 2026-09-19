import { isAccessPolicy, isAudit, isPage, isProject, isRecord, isSession, isUuid } from './types';
import type { AccessPolicyWrite, ProjectCreate } from './types';

export type FieldError = { pointer: string; code: string };
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    public readonly requestId: string | null = null,
    public readonly fields: FieldError[] = [],
    public readonly retryAt = 0,
  ) {
    super(code);
    this.name = 'ApiError';
  }
}
export const asApiError = (error: unknown): ApiError => error instanceof ApiError
  ? error : new ApiError(0, 'network_error');
export const isAborted = (error: unknown): boolean => error instanceof DOMException && error.name === 'AbortError';
export type ApiResult<T> = { data: T; etag: string | null; requestId: string | null };
type Options = { method?: 'GET' | 'POST' | 'PUT'; body?: unknown; csrf?: string; key?: string; etag?: string; signal?: AbortSignal };

export function retryTime(header: string | null, now = Date.now()): number {
  if (!header) return 0;
  if (/^\d+$/.test(header)) {
    const seconds = Number(header);
    return Number.isSafeInteger(seconds) ? now + seconds * 1000 : 0;
  }
  const date = Date.parse(header);
  return Number.isFinite(date) ? Math.max(now, date) : 0;
}

async function pause(ms: number, signal?: AbortSignal): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    if (signal?.aborted) { reject(new DOMException('Aborted', 'AbortError')); return; }
    const abort = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); };
    const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, ms);
    signal?.addEventListener('abort', abort, { once: true });
  });
}

type ResponseValue = { response: Response; value: unknown; validJson: boolean };

async function readJson(response: Response, signal: AbortSignal): Promise<{ value: unknown; validJson: boolean }> {
  if (response.status === 204) return { value: undefined, validJson: true };
  const reader = response.body?.getReader();
  if (!reader) return { value: undefined, validJson: false };
  const cancel = () => { void reader.cancel().catch(() => undefined); };
  signal.addEventListener('abort', cancel, { once: true });
  let bytes = 0;
  let body = '';
  const decoder = new TextDecoder('utf-8', { fatal: true });
  try {
    while (true) {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      const chunk = await reader.read();
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      if (chunk.done) break;
      bytes += chunk.value.byteLength;
      // SP-01 pages are capped at 25 records; this also bounds malformed responses.
      if (bytes > 1024 * 1024) {
        cancel();
        throw new ApiError(0, 'unexpected_response');
      }
      body += decoder.decode(chunk.value, { stream: true });
    }
    body += decoder.decode();
    try { return { value: JSON.parse(body) as unknown, validJson: true }; }
    catch { return { value: undefined, validJson: false }; }
  } finally {
    signal.removeEventListener('abort', cancel);
    reader.releaseLock();
  }
}

async function attempt(path: string, options: Options): Promise<ResponseValue> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  options.signal?.addEventListener('abort', abort, { once: true });
  if (options.signal?.aborted) controller.abort();
  const timeout = setTimeout(abort, 15_000);
  const headers = new Headers({ Accept: 'application/json, application/problem+json' });
  if (options.body !== undefined) headers.set('Content-Type', 'application/json');
  if (options.csrf) headers.set('X-CSRF-Token', options.csrf);
  if (options.key) headers.set('Idempotency-Key', options.key);
  if (options.etag) headers.set('If-Match', options.etag);
  try {
    const response = await fetch(path, {
      method: options.method ?? 'GET', credentials: 'same-origin', cache: 'no-store', redirect: 'error',
      headers, signal: controller.signal,
      ...(options.body !== undefined ? { body: JSON.stringify(options.body) } : {}),
    });
    const body = await readJson(response, controller.signal);
    return { response, ...body };
  } catch (error) {
    if (options.signal?.aborted) throw error;
    if (error instanceof ApiError) throw error;
    throw new ApiError(0, controller.signal.aborted ? 'request_timeout' : 'network_error');
  } finally {
    clearTimeout(timeout);
    options.signal?.removeEventListener('abort', abort);
  }
}

function readProblem(response: Response, value: unknown): ApiError {
  const headerId = response.headers.get('X-Request-ID');
  const requestId = isUuid(headerId) ? headerId : null;
  const retryAt = retryTime(response.headers.get('Retry-After'));
  if (!isRecord(value)) return new ApiError(response.status, 'unexpected_response', requestId, [], retryAt);
  const fields: FieldError[] = [];
  if (Array.isArray(value.errors)) {
    for (const item of value.errors.slice(0, 100)) {
      if (isRecord(item) && typeof item.pointer === 'string' && item.pointer.length <= 1024 &&
          typeof item.code === 'string' && /^[a-z_]{1,64}$/.test(item.code)) {
        fields.push({ pointer: item.pointer, code: item.code });
      }
    }
  }
  const code = typeof value.code === 'string' && /^[a-z_]{1,64}$/.test(value.code) ? value.code : 'unexpected_response';
  return new ApiError(response.status, code, requestId ?? (isUuid(value.request_id) ? value.request_id : null), fields, retryAt);
}

export async function request<T>(path: string, validate: (value: unknown) => value is T, options: Options = {}): Promise<ApiResult<T>> {
  if (!path.startsWith('/api/v1/')) throw new ApiError(0, 'invalid_api_path');
  for (let count = 0; ; count++) {
    const { response, value, validJson } = await attempt(path, options);
    if (!response.ok) {
      const error = readProblem(response, value);
      const wait = Math.max(1000 * (count + 1), error.retryAt - Date.now());
      if ((options.method ?? 'GET') === 'GET' && [429, 503].includes(error.status) && count < 2 && wait <= 2000) {
        await pause(wait, options.signal);
        continue;
      }
      throw error;
    }
    const id = response.headers.get('X-Request-ID');
    const requestId = isUuid(id) ? id : null;
    if (!validJson || !validate(value)) throw new ApiError(0, 'unexpected_response', requestId);
    return { data: value, etag: response.headers.get('ETag'), requestId };
  }
}

const withSignal = (signal?: AbortSignal): Options => signal ? { signal } : {};
const query = (cursor: string | null, q = '') => {
  const params = new URLSearchParams({ limit: '25' });
  if (cursor) params.set('cursor', cursor);
  if (q) params.set('q', q);
  return params.toString();
};
const projectPath = (id: string) => `/api/v1/projects/${encodeURIComponent(id)}`;
export const api = {
  session: (signal?: AbortSignal) => request('/api/v1/session', isSession, withSignal(signal)),
  logout: (csrf: string) => request('/api/v1/session/logout', (v): v is undefined => v === undefined, { method: 'POST', csrf }),
  projects: (cursor: string | null, q: string, signal?: AbortSignal) => request(`/api/v1/projects?${query(cursor, q)}`, isPage(isProject), withSignal(signal)),
  createProject: (body: ProjectCreate, csrf: string, key: string) => request('/api/v1/projects', isProject, { method: 'POST', body, csrf, key }),
  project: (id: string, signal?: AbortSignal) => request(projectPath(id), isProject, withSignal(signal)),
  access: (id: string, signal?: AbortSignal) => request(`${projectPath(id)}/access-policy`, isAccessPolicy, withSignal(signal)),
  saveAccess: (id: string, body: AccessPolicyWrite, csrf: string, etag: string, key: string) =>
    request(`${projectPath(id)}/access-policy`, isAccessPolicy, { method: 'PUT', body, csrf, etag, key }),
  audit: (id: string, cursor: string | null, signal?: AbortSignal) => request(`${projectPath(id)}/audit?${query(cursor)}`, isPage(isAudit), withSignal(signal)),
};
