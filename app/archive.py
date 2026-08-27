"""CR-022 snapshot archive (EMM-F2) — content-addressed input evidence store.

Implements the F2-D1…D10 authority decisions:

* F2-D1 — archives BOTH raw source bytes (audit evidence of what was received)
  and the canonical normalized FoundationPayload corpus (replay/audit anchor).
  Derived output is never archived as a substitute for either.
* F2-D2 — per run/source slot retains raw bytes, per-file SHA-256, filename,
  declared source as_of, ingestion timestamp, row counts, parse status, parse
  warnings, plus the normalized foundation, a policy document snapshot, all
  version lineages, run linkage, input/output hashes, and blob linkage.
* F2-D6 — integrity model, documented precisely:
    - Blobs are content-addressed: path = ``blobs/<sha256[:2]>/<sha256>``.
    - Blob creation is write-once and idempotent: identical bytes → no-op;
      any byte mismatch at an existing path raises ArchiveIntegrityError.
      The module exposes NO update/delete/mutation API of any kind.
    - The manifest is append-only JSONL. Every entry carries ``seq`` (line
      index), ``prev_entry_hash`` (SHA-256 of the previous entry's canonical
      body; ``null`` at genesis) and ``entry_hash`` (SHA-256 of the canonical
      JSON of the entry minus the ``entry_hash`` key).
    - ``verify()`` re-walks the chain, recomputes every entry hash, and
      re-hashes every referenced blob — detecting modification, reordering
      and mid-chain removal.
    - NOT guaranteed (stated honestly): this is a local-filesystem store, not
      WORM media — a sufficiently privileged local actor could rewrite the
      whole tree; undetectable tail truncation requires an external anchor.
      No off-box replication or cryptographic timestamping exists in CR-022.
* F2-D7 — archives live under the gitignored ``data/archive`` boundary with
  indefinite local retention. No compression/rotation/deletion in CR-022.

Payload determinism (Freeze §8): wall-clock values (``ingested_at``,
``appended_at``) and the hash chain appear ONLY in manifest entries, never in
the decision/foundation payload. The payload-visible ``provenance.archive``
block built by ``archive_identity()`` is fully content-derived, so identical
inputs still hash identically.
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .determinism import canonical_json

MANIFEST_NAME = "manifest.jsonl"
BLOB_DIR_NAME = "blobs"


class ArchiveIntegrityError(RuntimeError):
    """Raised when existing archive content disagrees with new identical-key
    content (the archive never silently overwrites)."""


# ---- paths ------------------------------------------------------------------


def _root(root=None) -> Path:
    return Path(root or config.ARCHIVE_ROOT)


def blob_relpath(sha256_hex: str) -> str:
    """Relative blob path for a content hash (POSIX-style, stored in records)."""
    return f"{BLOB_DIR_NAME}/{sha256_hex[:2]}/{sha256_hex}"


def blob_path_for(sha256_hex: str, root=None) -> Path:
    return _root(root) / BLOB_DIR_NAME / sha256_hex[:2] / sha256_hex


def manifest_path(root=None) -> Path:
    return _root(root) / MANIFEST_NAME


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- content-addressed blob store (write-once) -------------------------------


def store_blob(payload: bytes, root=None) -> str:
    """Write ``payload`` once under its SHA-256 identity; return the hex digest.

    Idempotent: if the blob already exists its content must hash identically —
    otherwise ArchiveIntegrityError (never an overwrite).
    """
    sha = hashlib.sha256(payload).hexdigest()
    dest = blob_path_for(sha, root)
    if dest.exists():
        existing = dest.read_bytes()
        if hashlib.sha256(existing).hexdigest() != sha:
            raise ArchiveIntegrityError(
                f"blob {blob_relpath(sha)} exists with different bytes — archive is write-once")
        return sha
    dest.parent.mkdir(parents=True, exist_ok=True)
    # 'xb' = O_EXCL create: no race can overwrite an existing blob.
    with open(dest, "xb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    return sha


def capture_bytes(slot: str, filename: str, payload: bytes, *,
                  declared_source_as_of: str | None = None,
                  as_of_source: str = "fallback_upload_mtime", root=None) -> dict:
    """Archive raw received bytes BEFORE any parsing; return the file record."""
    sha = store_blob(payload, root)
    return {
        "slot": slot,
        "filename": filename,
        "sha256": sha,
        "size_bytes": len(payload),
        "blob": blob_relpath(sha),
        "declared_source_as_of": declared_source_as_of,
        "as_of_source": as_of_source,
        "ingested_at": _utcnow(),
        "rows": None,
        "parse_status": None,
        "parse_warnings": [],
    }


def capture_file(slot: str, path, *, declared_source_as_of: str | None = None,
                 as_of_source: str = "fallback_upload_mtime", root=None) -> dict:
    """Archive the exact bytes of ``path`` (idempotent) and return the record."""
    p = Path(path)
    return capture_bytes(slot, p.name, p.read_bytes(),
                         declared_source_as_of=declared_source_as_of,
                         as_of_source=as_of_source, root=root)


def capture_policy(root=None) -> dict:
    """Archive the current policy document (policy/policy.yaml) bytes as-is."""
    return capture_file("policy", config.POLICY_PATH,
                        declared_source_as_of=None,
                        as_of_source="policy_document", root=root)


# ---- normalized foundation corpus blob (F2-D5) --------------------------------


def foundation_blob_bytes(corpus: dict) -> bytes:
    """Deterministic canonical serialization of the normalized engine input.

    The corpus is the decision-relevant FoundationPayload minus identity/hash
    fields and minus the archive block itself, so it contains no hashes at all
    (no self-reference cycle). Hash-stable by construction: canonical JSON.
    """
    return canonical_json(corpus).encode("utf-8")


def store_foundation(corpus: dict, root=None) -> str:
    """Archive the canonical normalized-foundation corpus; return its SHA-256."""
    return store_blob(foundation_blob_bytes(corpus), root)


def read_blob(sha256_hex: str, root=None) -> bytes:
    return blob_path_for(sha256_hex, root).read_bytes()


# ---- payload-visible archive identity (F2-D4, deterministic) ------------------


def archive_identity(foundation_sha256: str, policy_sha256: str,
                     themes_sha256: str | None = None) -> dict:
    """Payload-visible archive provenance block — fully content-derived.

    Embedded in ``provenance.archive`` before the payload content hash is
    computed, so payload hash semantics stay exactly 'sha256 of the canonical
    payload minus run_id'. Only LOGICAL-content identities are embedded
    (normalized-foundation corpus hash, policy document hash, archive
    version/manifest identity) — never raw received-byte hashes, wall-clock
    values or chain hashes, which are event/byte specific and would break
    logical-input hash equivalence (CR-005) and determinism (Freeze §8).
    Per-file raw SHA-256, ingested_at and the hash chain live only in the
    manifest, reachable via run_id from any persisted run payload.
    CR-023: ``themes_sha256`` (integrity hash of the authority theme mapping
    document) is included whenever a theme document participated in the run.
    """
    block = {
        "archive_version": config.ARCHIVE_VERSION,
        "manifest": MANIFEST_NAME,
        "foundation_sha256": foundation_sha256,
        "policy_sha256": policy_sha256,
    }
    if themes_sha256 is not None:
        block["themes_sha256"] = themes_sha256
    return block


# ---- append-only hash-chained manifest (F2-D6) ---------------------------------


def read_manifest(root=None) -> list[dict]:
    path = manifest_path(root)
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def _entry_hash(entry_without_hash: dict) -> str:
    return hashlib.sha256(canonical_json(entry_without_hash).encode("utf-8")).hexdigest()


def append_entry(entry: dict, root=None) -> dict:
    """Append one manifest entry (kind-specific body) with chain fields."""
    path = manifest_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = read_manifest(root)
    seq = len(entries)
    prev = entries[-1]["entry_hash"] if entries else None
    body = {**entry, "archive_version": config.ARCHIVE_VERSION,
            "seq": seq, "prev_entry_hash": prev}
    body["entry_hash"] = _entry_hash(body)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(body, sort_keys=True, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return body


def append_ingest(*, run_id, run_as_of, input_hash, files, foundation_sha256,
                  policy_sha256, policy_version, root=None) -> dict:
    """Manifest entry for one ingestion event (run_foundation path, F2-D2)."""
    return append_entry({
        "kind": "ingest",
        "run_id": run_id,
        "appended_at": _utcnow(),
        "run_as_of": run_as_of,
        "input_hash": input_hash,
        "engine_version": config.ENGINE_VERSION,
        "normalization_version": config.NORMALIZATION_VERSION,
        "calculation_version": config.CALCULATION_VERSION,
        "policy_version": policy_version,
        "files": list(files),
        "foundation_sha256": foundation_sha256,
        "foundation_blob": blob_relpath(foundation_sha256),
        "policy_sha256": policy_sha256,
        "policy_blob": blob_relpath(policy_sha256),
    }, root=root)


def append_slot(*, run_id, file_record, policy_version, root=None) -> dict:
    """Manifest entry for an extra per-run source slot (e.g. sold.csv, F2-D2)."""
    return append_entry({
        "kind": "slot",
        "run_id": run_id,
        "appended_at": _utcnow(),
        "engine_version": config.ENGINE_VERSION,
        "policy_version": policy_version,
        "file": file_record,
    }, root=root)


def append_run_link(*, run_id, input_hash, decision_content_hash,
                    policy_version, root=None) -> dict:
    """Manifest entry linking a persisted decision run to its ingest evidence."""
    return append_entry({
        "kind": "run_link",
        "run_id": run_id,
        "appended_at": _utcnow(),
        "engine_version": config.ENGINE_VERSION,
        "policy_version": policy_version,
        "input_hash": input_hash,
        "decision_content_hash": decision_content_hash,
    }, root=root)


# ---- tamper detection (F2-D6) ---------------------------------------------------


def _check_blob_reference(errors, where, rel_or_sha, root_path):
    try:
        sha_from_path = rel_or_sha.split("/")[-1]
        data = blob_path_for(sha_from_path, root_path).read_bytes()
    except (OSError, IndexError):
        errors.append(f"{where}: referenced blob missing ({rel_or_sha})")
        return
    actual = hashlib.sha256(data).hexdigest()
    if actual != sha_from_path:
        errors.append(f"{where}: blob content mismatch ({sha_from_path} != {actual})")


def verify(root=None) -> dict:
    """Tamper-detection walk: parse, chain, entry hashes, referenced blobs.

    Returns {"ok": bool, "errors": [...], "warnings": [...], "entries": int}.
    Detects: modified manifest bodies, chain breaks, reordering, mid-chain
    removal, missing or modified blobs. Does NOT claim detection of whole-tree
    rewrite or tail truncation without an external anchor (documented in the
    module docstring).
    """
    root_path = _root(root)
    errors: list[str] = []
    warnings: list[str] = []
    path = manifest_path(root_path)
    parsed: list[dict] = []
    if path.exists():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                parsed.append(json.loads(line))
            except json.JSONDecodeError as exc:
                errors.append(f"manifest line {lineno}: unparseable JSON ({exc})")
    for i, entry in enumerate(parsed):
        at = f"manifest entry {i}"
        if entry.get("seq") != i:
            errors.append(f"{at}: seq {entry.get('seq')!r} != line index {i}")
        expected_prev = parsed[i - 1]["entry_hash"] if i else None
        if entry.get("prev_entry_hash") != expected_prev:
            errors.append(f"{at}: prev_entry_hash chain break")
        body = {k: v for k, v in entry.items() if k != "entry_hash"}
        if _entry_hash(body) != entry.get("entry_hash"):
            errors.append(f"{at}: entry_hash mismatch (body modified?)")
        kind = entry.get("kind")
        if kind == "ingest":
            for rec in entry.get("files", []):
                _check_blob_reference(errors, f"{at} file {rec.get('slot')}",
                                      rec.get("blob", ""), root_path)
            for label, rel in (("foundation", entry.get("foundation_blob")),
                               ("policy", entry.get("policy_blob"))):
                if rel:
                    _check_blob_reference(errors, f"{at} {label}", rel, root_path)
        elif kind == "slot":
            rec = entry.get("file") or {}
            _check_blob_reference(errors, f"{at} file {rec.get('slot')}",
                                  rec.get("blob", ""), root_path)
    # Orphan blobs: present on disk but unreferenced (informational).
    referenced = set()
    for entry in parsed:
        for rec in entry.get("files", []):
            referenced.add(rec.get("blob"))
        if entry.get("foundation_blob"):
            referenced.add(entry["foundation_blob"])
        if entry.get("policy_blob"):
            referenced.add(entry["policy_blob"])
        rec = entry.get("file")
        if isinstance(rec, dict):
            referenced.add(rec.get("blob"))
    blobs_dir = root_path / BLOB_DIR_NAME
    if blobs_dir.exists():
        for p in sorted(blobs_dir.rglob("*")):
            if p.is_file():
                rel = p.relative_to(root_path).as_posix()
                if rel not in referenced:
                    warnings.append(f"orphan blob on disk: {rel}")
    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "entries": len(parsed)}


def run_entries(run_id, root=None) -> list[dict]:
    """All manifest entries linked to a run (ingest / slot / run_link)."""
    return [e for e in read_manifest(root) if e.get("run_id") == run_id]
