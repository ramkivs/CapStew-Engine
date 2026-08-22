// Single fetch boundary — components never construct raw fetch() calls (UI-1 gate).
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail: string = res.statusText;
    try { detail = JSON.stringify(await res.json()); } catch { /* non-JSON */ }
    throw new Error(`${res.status} ${detail}`);
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
