import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, retryTime } from '../src/api/client';
import { json, policy, principalId, problem, project, projectId, requestId, session } from './fixtures';

afterEach(() => vi.useRealTimers());

describe('SPEC-0001/0017 browser API boundary', () => {
  it('uses cookies and CSRF, never bearer tokens; create carries an explicit idempotency key', async () => {
    const fetcher = vi.fn().mockResolvedValue(json(project, 201));
    vi.stubGlobal('fetch', fetcher);
    const key = crypto.randomUUID();
    await api.createProject({ name: project.name, description: project.description }, session.csrf_token!, key);
    expect(fetcher).toHaveBeenCalledTimes(1);
    const init = fetcher.mock.calls[0]?.[1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(init.credentials).toBe('same-origin');
    expect(init.cache).toBe('no-store');
    expect(headers.get('Authorization')).toBeNull();
    expect(headers.get('X-CSRF-Token')).toBe(session.csrf_token);
    expect(headers.get('Idempotency-Key')).toBe(key);
  });

  it('sends conditional policy replacement without silently deriving a new ETag', async () => {
    const fetcher = vi.fn().mockResolvedValue(json(policy));
    vi.stubGlobal('fetch', fetcher);
    const etag = `"acl:${projectId}:1"`;
    await api.saveAccess(projectId, { members: policy.members }, session.csrf_token!, etag, crypto.randomUUID());
    const init = fetcher.mock.calls[0]?.[1] as RequestInit;
    expect(new Headers(init.headers).get('If-Match')).toBe(etag);
    expect(JSON.parse(init.body as string)).toEqual({ members: [{ principal_id: principalId, role: 'owner' }] });
  });

  it.each([401, 403, 404, 409, 412, 422])('does not retry status %s', async (status) => {
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(problem(status)));
    vi.stubGlobal('fetch', fetcher);
    await expect(api.project(projectId)).rejects.toMatchObject({ status, requestId });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('does not automatically retry an uncertain mutation', async () => {
    const fetcher = vi.fn().mockRejectedValue(new TypeError('Network'));
    vi.stubGlobal('fetch', fetcher);
    await expect(api.createProject({ name: 'A', description: '' }, session.csrf_token!, crypto.randomUUID())).rejects.toMatchObject({ status: 0, code: 'network_error' });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('safe-read retry respects Retry-After and is bounded', async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(problem(503, 'unavailable', { 'Retry-After': '1' })));
    vi.stubGlobal('fetch', fetcher);
    const result = api.project(projectId).catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(999);
    expect(fetcher).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(fetcher).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(2000);
    expect(await result).toBeInstanceOf(ApiError);
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it('does not shorten a longer Retry-After', async () => {
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(problem(429, 'rate_limited', { 'Retry-After': '30' })));
    vi.stubGlobal('fetch', fetcher);
    const before = Date.now();
    await expect(api.project(projectId)).rejects.toSatisfy((error: ApiError) => error.retryAt >= before + 30_000);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('supports HTTP date Retry-After and ignores malformed values', () => {
    const now = Date.parse('2026-09-19T10:00:00Z');
    expect(retryTime('Sat, 19 Sep 2026 10:00:30 GMT', now)).toBe(now + 30_000);
    expect(retryTime('invalid', now)).toBe(0);
  });

  it('rejects response shape drift and does not reflect the response body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ ...project, owner_secret: 'do-not-display' })));
    await expect(api.project(projectId)).rejects.toMatchObject({ code: 'unexpected_response', requestId });
  });

  it('keeps the 15-second deadline through a stalled response body and cancels its reader', async () => {
    vi.useFakeTimers();
    const canceled = vi.fn();
    const body = new ReadableStream<Uint8Array>({ start(controller) { controller.enqueue(new TextEncoder().encode('{')); }, cancel: canceled });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { headers: { 'Content-Type': 'application/json' } })));
    const result = api.project(projectId).catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(15_000);
    expect(await result).toMatchObject({ status: 0, code: 'request_timeout' });
    expect(canceled).toHaveBeenCalledTimes(1);
  });

  it('caller abort cancels a stalled response body before the deadline', async () => {
    const canceled = vi.fn();
    const body = new ReadableStream<Uint8Array>({ cancel: canceled });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body)));
    const controller = new AbortController();
    const result = api.project(projectId, controller.signal).catch((error: unknown) => error);
    await Promise.resolve();
    await Promise.resolve();
    controller.abort();
    expect(await result).toMatchObject({ name: 'AbortError' });
    expect(canceled).toHaveBeenCalledTimes(1);
  });

  it('keeps safe pointer errors but ignores untrusted titles and invalid request IDs', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ title: 'secret', code: 'validation_failed', request_id: 'secret', errors: [{ pointer: '/name', code: 'invalid' }] }), { status: 422, headers: { 'X-Request-ID': 'secret' } })));
    await expect(api.createProject({ name: 'A', description: '' }, session.csrf_token!, crypto.randomUUID())).rejects.toMatchObject({ requestId: null, message: 'validation_failed', fields: [{ pointer: '/name', code: 'invalid' }] });
  });
});
