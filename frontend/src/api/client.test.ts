import { describe, it, expect, vi, afterEach } from 'vitest';
import { api, ApiRequestError, ENGINE_UNREACHABLE, isNotFound, errMessage } from './client';

const realFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = realFetch; });

describe('api client — uniform error envelope', () => {
  it('returns parsed JSON on success', async () => {
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 })) as never;
    await expect(api.get('/health')).resolves.toEqual({ ok: true });
  });

  it('turns the backend envelope into an ApiRequestError carrying the code', async () => {
    const body = { error: { code: 'ENGINE_UNAVAILABLE', severity: 'error', message: 'Run failed', details: { detail: 'boom' } } };
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify(body), { status: 500 })) as never;
    await expect(api.get('/run-sample')).rejects.toMatchObject({ status: 500, code: 'ENGINE_UNAVAILABLE' });
  });

  it('exposes details so callers can render available_fy', async () => {
    // matches app/main.py: /tax-tracker?fy=<unknown> → 404 NOT_FOUND + available_fy
    const body = { error: { code: 'NOT_FOUND', severity: 'warning',
                            message: 'unknown financial year', details: { available_fy: ['2026-27'] } } };
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify(body), { status: 404 })) as never;
    try {
      await api.get('/tax-tracker?fy=1999-00');
      throw new Error('expected a throw');
    } catch (e) {
      expect(e).toBeInstanceOf(ApiRequestError);
      expect((e as ApiRequestError).details).toEqual({ available_fy: ['2026-27'] });
      expect(isNotFound(e)).toBe(true);
      expect(errMessage(e)).toContain('NOT_FOUND');
    }
  });

  it('degrades to ENGINE_UNREACHABLE when the engine is not running', async () => {
    globalThis.fetch = vi.fn(async () => { throw new TypeError('Failed to fetch'); }) as never;
    await expect(api.get('/health')).rejects.toMatchObject({ status: 0, code: ENGINE_UNREACHABLE });
  });

  it('survives a non-JSON error body', async () => {
    globalThis.fetch = vi.fn(async () => new Response('<html>502</html>', { status: 502 })) as never;
    await expect(api.get('/health')).rejects.toMatchObject({ status: 502 });
  });

  it('errMessage renders code and status for display', () => {
    expect(errMessage(new ApiRequestError(0, ENGINE_UNREACHABLE, 'not reachable')))
      .toContain('ENGINE_UNREACHABLE');
    expect(errMessage(new Error('plain'))).toContain('plain');
    expect(errMessage('a string')).toBe('a string');
  });
});
