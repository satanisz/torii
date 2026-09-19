const unavailable = 'Usługa demonstracyjna jest niedostępna.';

/** Bounded same-origin transport. Never retries a potentially completed write. */
export async function demoRequest<T = unknown>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController();
  const abort = () => { controller.abort(); };
  if (signal?.aborted) controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  const timer = setTimeout(abort, 15_000);
  try {
    const response = await fetch(`/demo-api${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { 'X-Torii-Demo': '1', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      signal: controller.signal, credentials: 'same-origin', cache: 'no-store', redirect: 'error',
    });
    let value: unknown;
    try { value = await response.json(); } catch { throw new Error(unavailable); }
    if (!response.ok) {
      const detail = value !== null && typeof value === 'object' && 'detail' in value ? value.detail : null;
      throw new Error(typeof detail === 'string' && detail.length <= 500 ? detail : unavailable);
    }
    return value as T;
  } catch (error) {
    if (controller.signal.aborted) throw new Error('Przekroczono czas oczekiwania. Odśwież stan przed ponownym zapisem.', { cause: error });
    if (error instanceof TypeError) throw new Error('Nie można połączyć się z lokalnym API. Sprawdź, czy demonstrator działa.', { cause: error });
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}

export function fileAsBase64(file: File): Promise<string> {
  if (!file.size || file.size > 5 * 1024 * 1024) return Promise.reject(new Error('Wybierz niepusty CSV o rozmiarze do 5 MiB.'));
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => { reject(new Error('Nie można odczytać pliku.')); };
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== 'string' || !result.includes(',')) reject(new Error('Nie można odczytać pliku.'));
      else resolve(result.slice(result.indexOf(',') + 1));
    };
    reader.readAsDataURL(file);
  });
}
