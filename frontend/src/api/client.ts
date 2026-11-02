// Single fetch boundary — components never construct raw fetch() calls (UI-1 gate).
import type { ApiError } from '../types';

/** Thrown when the engine is not reachable at all (backend down / wrong port). */
export const ENGINE_UNREACHABLE = 'ENGINE_UNREACHABLE';

/** An API failure, carrying the documented error code so callers can tell a
 *  benign "nothing to show yet" (NOT_FOUND) from a real fault. */
export class ApiRequestError extends Error {
  status: number;
  code: string;
  /** Backend `error.details`, e.g. `{ available_fy: [...] }` for a bad `?fy=`. */
  details: Record<string, unknown> | null;

  constructor(status: number, code: string, message: string,
              details: Record<string, unknown> | null = null) {
    super(message);
    this.name = 'ApiRequestError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function isEnvelope(body: unknown): body is ApiError {
  return !!body && typeof body === 'object' && 'error' in body
    && typeof (body as ApiError).error?.message === 'string';
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    // Network failure — the engine is not reachable at all.
    throw new ApiRequestError(0, ENGINE_UNREACHABLE,
      'Cannot reach the Capital Steward engine. Is the backend running on port 8000?');
  }
  if (!res.ok) {
    let code = 'ERROR';
    let message = res.statusText || `HTTP ${res.status}`;
    let details: Record<string, unknown> | null = null;
    try {
      const body: unknown = await res.json();
      if (isEnvelope(body)) {
        code = body.error.code;
        message = body.error.message;
        const d = body.error.details;
        if (d && typeof d === 'object') details = d as Record<string, unknown>;
      } else if (body && typeof body === 'object') {
        message = JSON.stringify(body);
      }
    } catch { /* non-JSON body — keep the status text */ }
    throw new ApiRequestError(res.status, code, message, details);
  }
  return res.json() as Promise<T>;
}

/** True when an error just means "there is nothing to display yet". */
export const isNotFound = (e: unknown): boolean =>
  e instanceof ApiRequestError && e.code === 'NOT_FOUND';

/** A short, user-facing message for any thrown value, with the code when known. */
export const errMessage = (e: unknown): string => {
  if (e instanceof ApiRequestError) return `${e.message} [${e.code}]`;
  return e instanceof Error ? e.message : String(e);
};

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
