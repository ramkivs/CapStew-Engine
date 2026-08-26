// Single fetch boundary — components never construct raw fetch() calls (UI-1 gate).

export interface ApiErrorBody {
  code?: string;
  severity?: string;
  stage?: string;
  file?: string;
  message?: string;
  details?: unknown;
}

export class ApiError extends Error {
  status: number;
  body: ApiErrorBody | null;

  constructor(status: number, message: string, body: ApiErrorBody | null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }

  get code(): string | null {
    return this.body?.code ?? null;
  }

  get stage(): string | null {
    return this.body?.stage ?? null;
  }

  get file(): string | null {
    return this.body?.file ?? null;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let body: ApiErrorBody | null = null;
    let message = res.statusText;
    try {
      const raw = await res.json();
      // Backend error envelope: { detail: { error: { code, stage?, file?, message } } }
      const err: ApiErrorBody | null = raw?.detail?.error ?? null;
      if (err && typeof err === 'object') {
        body = err;
        const where = [err.stage, err.file].filter(Boolean).join(' · ');
        message = `${err.code ?? 'ERROR'}${where ? ` · ${where}` : ''} — ${err.message ?? message}`;
      } else if (typeof raw?.detail === 'string') {
        message = raw.detail;
      } else {
        message = JSON.stringify(raw);
      }
    } catch { /* non-JSON error body — keep statusText */ }
    throw new ApiError(res.status, `${res.status} ${message}`, body);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T,>(p: string) => request<T>(p),
  post: <T,>(p: string, body?: unknown) =>
    request<T>(p, {
      method: 'POST',
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  put: <T,>(p: string, body: unknown) =>
    request<T>(p, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  postForm: <T,>(p: string, form: FormData) => request<T>(p, { method: 'POST', body: form }),
};
