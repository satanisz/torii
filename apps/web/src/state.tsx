import { createContext, useCallback, useContext, useEffect, useReducer, useRef, useState } from 'react';
import { useBlocker } from 'react-router-dom';
import { asApiError, isAborted } from './api/client';
import type { ApiError, ApiResult } from './api/client';
import type { Session } from './api/types';
import { text } from './i18n/pl';

export const SessionContext = createContext<{ session: Session; expire: () => void } | null>(null);
export function useSession() {
  const context = useContext(SessionContext);
  if (!context) throw new Error('Session context required');
  return context;
}
export type ReadState<T> = { status: 'loading' } | { status: 'ready'; value: ApiResult<T> } | { status: 'error'; error: ApiError };

export function useRead<T>(load: (signal: AbortSignal) => Promise<ApiResult<T>>, denied?: (error: ApiError) => void) {
  const { expire } = useSession();
  const [revision, trigger] = useReducer((n: number) => n + 1, 0);
  const [state, setState] = useState<ReadState<T>>({ status: 'loading' });
  const active = useRef<AbortController | null>(null);
  const invalidate = useCallback(() => {
    active.current?.abort();
    setState({ status: 'loading' });
  }, []);
  const reload = useCallback(() => { invalidate(); trigger(); }, [invalidate]);
  useEffect(() => {
    const controller = new AbortController();
    active.current = controller;
    setState({ status: 'loading' });
    void load(controller.signal).then((value) => {
      if (!controller.signal.aborted) setState({ status: 'ready', value });
    }).catch((error: unknown) => {
      if (controller.signal.aborted || isAborted(error)) return;
      const problem = asApiError(error);
      if (problem.status === 401) expire();
      if ([403, 404].includes(problem.status)) denied?.(problem);
      setState({ status: 'error', error: problem });
    });
    return () => controller.abort();
  }, [load, revision, expire, denied]);
  return { state, reload, invalidate };
}

export function useDirtyGuard(dirty: boolean) {
  const blocker = useBlocker(dirty);
  useEffect(() => {
    if (blocker.state === 'blocked') {
      if (window.confirm(text.dirtyPrompt)) blocker.proceed();
      else blocker.reset();
    }
  }, [blocker]);
  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    const confirmDiscard = (event: Event) => { if (!window.confirm(text.dirtyPrompt)) event.preventDefault(); };
    window.addEventListener('beforeunload', beforeUnload);
    window.addEventListener('torii:discard', confirmDiscard);
    return () => {
      window.removeEventListener('beforeunload', beforeUnload);
      window.removeEventListener('torii:discard', confirmDiscard);
    };
  }, [dirty]);
}

export const confirmDiscard = () => window.dispatchEvent(new Event('torii:discard', { cancelable: true }));

export function useRetryReady(error: ApiError | null) {
  const deadline = error?.retryAt ?? 0;
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    setNow(Date.now());
    if (deadline <= Date.now()) return;
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, [deadline]);
  return deadline <= now;
}

export function useMutationFailure(denied?: (error: ApiError) => void) {
  const { expire } = useSession();
  return useCallback((error: unknown) => {
    const problem = asApiError(error);
    if (problem.status === 401) expire();
    if ([403, 404].includes(problem.status)) denied?.(problem);
    return problem;
  }, [denied, expire]);
}
