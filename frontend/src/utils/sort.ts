// CR-026 (R-SORT-001): presentation-only holdings-table sorting primitives.
//
// Freeze §7 [FROZEN]: "Permitted client-side operations: formatting, sorting,
// filtering, colouring, rendering. Nothing that produces a decision or score."
// These comparators only RE-ORDER already-rendered payload fields; they produce
// no decision-relevant number. Locale-dependent collation is never used
// (determinism across browsers/OS locales, consistent with the engine's
// no-heuristic/no-fuzzy-matching posture extended to presentation).

export type SortDir = 'asc' | 'desc';

export interface SortState<K extends string = string> {
  key: K;
  dir: SortDir;
}

/**
 * Fixed interaction cycle: none → asc → desc → none. Single-column sorting only —
 * clicking any column starts (or restarts) that column at ascending.
 */
export function cycleSort<K extends string>(
  current: SortState<K> | null,
  key: K,
): SortState<K> | null {
  if (current === null || current.key !== key) return { key, dir: 'asc' };
  if (current.dir === 'asc') return { key, dir: 'desc' };
  return null;
}

/**
 * Deterministic code-point comparison — NOT locale collation (no localeCompare,
 * no Intl.Collator). Primary: case-folded code-point order; tie-break: raw
 * code-point order. Total, transitive, and identical in every environment.
 */
export function cmpCodePoint(a: string, b: string): number {
  const af = a.toLowerCase();
  const bf = b.toLowerCase();
  if (af < bf) return -1;
  if (af > bf) return 1;
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}

export type SortValue = string | number | null | undefined;

/**
 * Build a total-order comparator for one sortable column.
 *
 * - numbers compare numerically; strings compare via cmpCodePoint.
 *   ISO `YYYY-MM-DD` dates are therefore chronological automatically (lexical ==
 *   chronological for the frozen backend `next_review_date` format).
 * - null/undefined sort LAST in BOTH directions: the null-placement branch is
 *   decided before and never multiplied by `dir`.
 * - Equal primaries (including null-vs-null) fall through to the deterministic
 *   secondary tie-break: Instrument (code-point, fixed direction). Any remaining
 *   tie resolves to original payload index because callers sort a payload-order
 *   copy with the ES2019-guaranteed stable Array.prototype.sort.
 */
export function comparatorFor<T>(
  get: (row: T) => SortValue,
  dir: SortDir,
  tieKey: (row: T) => string | null | undefined,
): (a: T, b: T) => number {
  const mul = dir === 'desc' ? -1 : 1;
  return (a, b) => {
    const va = get(a);
    const vb = get(b);
    const aNull = va === null || va === undefined;
    const bNull = vb === null || vb === undefined;
    if (!aNull || !bNull) {
      if (aNull) return 1; // nulls LAST in both directions
      if (bNull) return -1;
      let c: number;
      if (typeof va === 'number' && typeof vb === 'number') {
        c = va < vb ? -1 : va > vb ? 1 : 0;
      } else {
        c = cmpCodePoint(String(va), String(vb));
      }
      if (c !== 0) return mul * c;
    }
    // Secondary tie-break: Instrument (code-point, fixed direction),
    // then original payload index via stable sort at the call site.
    return cmpCodePoint(tieKey(a) ?? '', tieKey(b) ?? '');
  };
}
