# CR-022 — Snapshot archiver / dated fundamentals store (EMM-F2)

**Status:** ~~IMPLEMENTED + VALIDATED (fixtures/synthetic only) — closure pending
authority-side real-data UAT.~~ **CLOSED (2026-08-28).** Authority-side real-data UAT
accepted; committed `8ea2e3d…` (CR-022); this archive is the evidence base consumed by
CR-024. Original point-in-time header preserved via strikethrough (CR-025/S2 convention).
**Authority gate:** F2-D1 through F2-D10 accepted verbatim from the EMM-F2
Discovery Record. **Branch:** `arena/01a033db-capstew-engine`.

## What CR-022 builds

Every ingestion event (`run_foundation` — i.e. `POST /run`, `POST /run-sample`,
`POST /ingest`) now leaves an **immutable, content-addressed evidence trail**
under `data/archive/` (gitignored, inside the existing local `data/` boundary,
indefinite retention):

```
data/archive/
├── blobs/<sha[:2]>/<sha256>     # content-addressed bytes: raw inputs,
│                                #  policy document, normalized foundation corpus
└── manifest.jsonl               # append-only, hash-chained event ledger
```

| Layer | Content | Addressing |
|---|---|---|
| Raw blobs | exact received bytes of every source slot (portfolio/screener/ledger/sold), captured **before any parsing** (`app/main.py` hook) | sha256(received bytes) |
| Policy blob | exact `policy/policy.yaml` bytes at run time | sha256(file bytes) |
| Foundation blob | canonical JSON of the normalized FoundationPayload corpus (positions/lots/reconciliation/warnings/as_of/provenance labels) — the exact engine input, sufficient to replay the run | sha256(canonical JSON) |
| Manifest | per-event entries: `ingest` / `slot` / `run_link` | seq + hash chain |

### Manifest entry fields (F2-D2 retention list)

`ingest`: run_id, run_as_of, input_hash, engine/normalization/calculation/policy
versions, per-file records `{slot, filename, sha256, size_bytes, blob,
declared_source_as_of, as_of_source, ingested_at, rows, parse_status,
parse_warnings}`, foundation_sha256 + foundation_blob, policy_sha256 +
policy_blob, `archive_version`, `seq`, `prev_entry_hash`, `entry_hash`,
`appended_at`.
`slot`: sold-file record linked by run_id. `run_link`: run_id ↔ input_hash ↔
decision content_hash.

## Integrity model (documented precisely — F2-D6)

* **Write-once blobs.** `archive.store_blob()` creates with `O_EXCL`; an
  existing path must hash identically or `ArchiveIntegrityError` is raised.
  The module exposes **no** update/delete/overwrite API. Identical re-ingestion
  is a no-op at the blob layer and a *new* appended entry at the ledger layer
  (never a mutation).
* **Append-only hash-chained ledger.** `entry_hash = sha256(canonical(body))`;
  each entry links `prev_entry_hash`; genesis is `null`. `seq` equals the line
  index.
* **`archive.verify()`** recomputes every entry hash, walks the chain, and
  re-hashes every referenced blob — detecting modification, reordering,
  mid-chain removal and missing/corrupt blobs (proven by
  `tests/test_cr022.py` tamper battery).
* **Honestly NOT claimed:** this is a local-filesystem store, not WORM media or
  an off-box ledger; a privileged local actor could rewrite the whole tree, and
  undetectable tail-truncation would require an external anchor. No
  compression/rotation/scheduling in CR-022 (F2-D7).

## Timestamp semantics (F2-D3)

Dual timestamps per slot: `declared_source_as_of` (explicit user declaration
via optional form fields `*_as_of` on /run and /ingest, or a documented
filename convention `…_DD_MM_YYYY` / `…_YYYY-MM-DD…`, day-first for DMY) wins
for the run's data-age semantics (incl. STALENESS — **thresholds unchanged**);
`ingested_at` (wall-clock receipt time) is recorded in the manifest. When no
declared date can be established, the upload-copy mtime remains, now
**explicitly labelled** `as_of_source: "fallback_upload_mtime"`. Non-ISO
declarations are rejected (HTTP 400), never coerced.

## Payload-visible provenance (F2-D4) and determinism (Freeze §8)

`payload.provenance.archive` = `{archive_version, manifest,
foundation_sha256, policy_sha256}` — deliberately **logical-content
identities only**. Raw received-byte hashes, wall-clock values and chain
hashes are event/byte-specific and live only in the manifest (reachable via
`run_id`), so logical-input hash equivalence (CR-005), what-if reproducibility
and the determinism guarantee are preserved exactly. The block is attached
before the payload content hash, so content-hash semantics remain literally
"sha256 of the canonical payload minus run_id". VP-1 applied:
ENGINE_VERSION `0.3.1-phase3` → `0.4.0-phase3`; CALCULATION_VERSION 2.1,
NORMALIZATION_VERSION 1.0 and policy_version are unchanged (no math,
normalizer or policy change).

## Status of the governed gaps

* **G-04 (own-5yr PE/PB median): STAYS OPEN, proxy preserved.** No valuation
  scoring change; peer-relative premiums remain the disclosed proxy
  (`data_quality.valuation_stretch: "proxy"` where fundamentals exist); the
  dated screener series now accumulates in the archive from activation forward.
  Closing G-04 requires a separate authority decision (F2-D8).
* **G-05 (quality time series): STAYS OPEN** until (1) dated screener snapshots
  are archived (now satisfied for activation-forward), (2) a quality series is
  computed from that archive (not implemented), and (3) authority separately
  authorizes activation of the relevant G1 legs (F2-D9). Pre-activation history
  remains explicitly unrecoverable.
* **EMM-F2/G1-HIST: reported source-dependent frozen-rule partial.** The G1
  quality-drop / pledge-QoQ history legs remain silent; CR-022 does not touch
  gate behavior (structurally asserted by `test_g05_remains_open_and_g1_history_legs_unfed`).

## Explicit non-scope (unchanged by this CR)

Decision mathematics, thresholds, taxonomy (six states), NO-DECISION/G0
behavior, hysteresis, trim modes, tax/sizing methodology, P7 meanings,
ACCUMULATE, UI surfaces, exports, compression/rotation, real-data fixtures,
certification status: **all untouched** (522-test suite green).

## Validation summary

* 497-test regression suite: **green** (1 legacy pin updated for the authorized
  VP-1 version bump; CR-005 logical-input equivalence preserved).
* `tests/test_cr022.py`: 25 proofs — raw-byte capture (incl. pre-parse capture
  of corrupt uploads), sha stability, normalized-corpus archive, manifest↔run
  linkage, policy snapshot, versions, **replay equivalence** (archived corpus
  re-derives input hash and reproduces the decision content hash), tamper
  detection (blob/manuscript/chain-break/reorder), repeated-run idempotence,
  distinct replacement identity, run-history shape unchanged, G-04 proxy
  label, G-05/G1-HIST absence guards, six-state taxonomy/distribution pin,
  dual-timestamp precedence + invalid-date rejection, what-if non-persistence.

## Real-data UAT (authority-side, before closure)

On the Windows authority environment with the real three-file export
(portfolio slot `TT_mystockholdings_26_08_2026.csv`, screener slot,
ledger slot): run `POST /run` and confirm (a) `data/archive/blobs/` contains
the three raw blobs whose SHA-256 match the local files, one foundation corpus
blob and one policy blob; (b) `manifest.jsonl` contains one `ingest` entry (and
one `run_link`) with matching hashes, and the portfolio slot records
`as_of_source: "declared_filename"`, `as_of: 2026-08-26`; (c) the payload
`provenance.archive` block shows `archive_version: 1`; (d) decisions and the
six-state distribution equal the pre-CR-022 run for the same inputs;
(e) re-running the same files appends new entries without altering existing
blobs (`verify()` ok). No real exports enter Git; the privacy firewall is
preserved (`data/` remains local and gitignored).
