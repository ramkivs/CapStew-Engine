import { describe, it, expect } from 'vitest';
import { comparatorFor, cmpCodePoint, cycleSort } from './sort';

describe('cycleSort — none → asc → desc → none', () => {
  it('starts a new column ascending', () => {
    expect(cycleSort(null, 'alloc')).toEqual({ key: 'alloc', dir: 'asc' });
  });
  it('advances asc → desc on the same column', () => {
    expect(cycleSort({ key: 'alloc', dir: 'asc' }, 'alloc')).toEqual({ key: 'alloc', dir: 'desc' });
  });
  it('returns to none on the third click', () => {
    expect(cycleSort({ key: 'alloc', dir: 'desc' }, 'alloc')).toBeNull();
  });
  it('restarts ascending when switching columns', () => {
    expect(cycleSort({ key: 'alloc', dir: 'desc' }, 'gain')).toEqual({ key: 'gain', dir: 'asc' });
  });
});

describe('cmpCodePoint — deterministic, locale-independent', () => {
  it('compares case-insensitively, then breaks the tie on raw code points', () => {
    expect(cmpCodePoint('Ashoka', 'bajaj')).toBe(-1);
    // primary (folded) comparison ties; the documented tie-break orders by raw
    // code point, so uppercase sorts before lowercase — a total, stable order.
    expect(cmpCodePoint('ASHOKA', 'ashoka')).toBe(-1);
    expect(cmpCodePoint('ashoka', 'ASHOKA')).toBe(1);
    expect(cmpCodePoint('same', 'same')).toBe(0);
  });
  it('orders deterministically regardless of environment locale', () => {
    const sorted = ['LT', 'ashoka', 'Bajaj', 'SALASAR'].sort(cmpCodePoint);
    expect(sorted).toEqual(['ashoka', 'Bajaj', 'LT', 'SALASAR']);
  });
});

type Row = { id: string; v: number | null };

describe('comparatorFor', () => {
  const tie = (r: Row) => r.id;

  it('sorts numbers numerically, not lexically', () => {
    const rows: Row[] = [{ id: 'a', v: 100 }, { id: 'b', v: 9 }, { id: 'c', v: 40 }];
    expect([...rows].sort(comparatorFor((r) => r.v, 'asc', tie)).map((r) => r.v))
      .toEqual([9, 40, 100]);
  });

  it('reverses on desc', () => {
    const rows: Row[] = [{ id: 'a', v: 1 }, { id: 'b', v: 3 }, { id: 'c', v: 2 }];
    expect([...rows].sort(comparatorFor((r) => r.v, 'desc', tie)).map((r) => r.v))
      .toEqual([3, 2, 1]);
  });

  it('puts nulls LAST in BOTH directions (NO-DECISION holdings)', () => {
    const rows: Row[] = [{ id: 'a', v: 5 }, { id: 'b', v: null }, { id: 'c', v: 1 }];
    const asc = [...rows].sort(comparatorFor((r) => r.v, 'asc', tie)).map((r) => r.id);
    const desc = [...rows].sort(comparatorFor((r) => r.v, 'desc', tie)).map((r) => r.id);
    expect(asc[asc.length - 1]).toBe('b');
    expect(desc[desc.length - 1]).toBe('b');
  });

  it('breaks ties deterministically by the tie key', () => {
    const rows: Row[] = [{ id: 'zeta', v: 5 }, { id: 'alpha', v: 5 }];
    expect([...rows].sort(comparatorFor((r) => r.v, 'asc', tie)).map((r) => r.id))
      .toEqual(['alpha', 'zeta']);
  });
});
