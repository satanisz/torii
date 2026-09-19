import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import type { ApiError } from './api/client';
import { text } from './i18n/pl';

export function Loading() { return <p className="status-line" role="status">{text.loading}</p>; }
export function errorMessage(error: ApiError): string {
  if (error.code === 'unexpected_response') return text.unexpected;
  if (error.status === 401) return text.sessionExpired;
  if (error.status === 403) return text.forbidden;
  if (error.status === 404) return text.notFound;
  if (error.status === 409 || error.status === 412) return text.conflict;
  if (error.status === 422) return text.validation;
  if (error.status === 429 || error.status === 503) return text.rateLimited;
  return text.networkError;
}
export function ErrorPanel({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (error.retryAt <= Date.now()) return;
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, [error.retryAt]);
  const waiting = error.retryAt > now;
  return <section className="notice danger" role="alert">
    <p>{errorMessage(error)}</p>
    {error.requestId && <p className="small">{text.requestId}: <code>{error.requestId}</code></p>}
    {waiting && <p className="small">{text.retryWait}</p>}
    {onRetry && <button className="secondary" onClick={onRetry} disabled={waiting}>{text.retry}</button>}
  </section>;
}
export function Field({ label, id, error, hint, children }: { label: string; id: string; error?: string | undefined; hint?: string; children: ReactNode }) {
  return <div className="field">
    <label htmlFor={id}>{label}</label>
    {children}
    {hint && <p id={`${id}-hint`} className="hint">{hint}</p>}
    {error && <p id={`${id}-error`} className="field-error">{error}</p>}
  </div>;
}
export function Identifier({ value }: { value: string }) {
  const [status, setStatus] = useState('');
  async function copy() {
    try { await navigator.clipboard.writeText(value); setStatus(text.copied); }
    catch { setStatus(text.copyFailed); }
  }
  return <span className="identifier"><code>{value}</code><button className="text-button" onClick={copy} aria-label={`${text.copy} ${value}`}>{text.copy}</button><span className="small" role="status">{status}</span></span>;
}
export function PageControls({ previous, next }: { previous?: (() => void) | undefined; next?: (() => void) | undefined }) {
  if (!previous && !next) return null;
  return <nav className="pagination" aria-label="Paginacja">
    <button className="secondary" disabled={!previous} onClick={previous}>{text.previous}</button>
    <button className="secondary" disabled={!next} onClick={next}>{text.next}</button>
  </nav>;
}
export function formatDate(value: string) { return new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)); }
