"""CR-023 / EMM-H2 — manual theme-tag layer (loader · validation · resolver).

Implements the H2-D1…D10 dispositions:

* Document = ``themes/themes.yaml`` — authority-controlled (H2-D5-A),
  versioned + effective-dated (H2-D6-A), provenance-bearing (H2-D7),
  schema_version 1. It is NOT policy.yaml and is not freely user-editable.
* Strict validation (no silent repair): known taxonomy themes only, exactly
  one assignment per instrument (H2-D8-A), required provenance fields,
  ISO effective dates, integer versions, structural integrity, deterministic
  loading. invalid => blocking error, never defaulted.
* Resolution is PURE: same (document bytes, instrument, as_of) always
  resolves identically (Freeze §8). Resolution honors effective dating:
  the document and each assignment apply only when their effective_from is
  on/before the run as_of; otherwise the position uses the sub_sector
  fallback (H2-D3-A) — labels stay honest: fallback is never re-labelled
  as manual.
* Rename/version discipline (H2-D9-A): ``validate_version_order`` asserts a
  new document version is strictly greater, theme IDs are immutable, and a
  changed theme name requires a rename_history entry; historical payloads
  and CR-022 archives are never re-labelled.
"""
import hashlib
from datetime import date
from pathlib import Path

import yaml

from . import config

SCHEMA_VERSION = 1
SOURCE_MANUAL = "manual"
SOURCE_FALLBACK = "fallback_sub_sector"

REQUIRED_DOC_FIELDS = ("schema_version", "document_version", "effective_from",
                       "owner", "source", "change_id", "taxonomy", "assignments")
REQUIRED_TAXONOMY_FIELDS = ("id", "name", "definition", "inclusion_rule",
                            "exclusion_rule")
REQUIRED_ASSIGNMENT_FIELDS = ("instrument", "theme", "owner", "source",
                              "effective_from", "version", "change_id")


# ---- loading (deterministic) -------------------------------------------------


def document_bytes(path=None):
    """Raw bytes of the authority document, or None when absent.

    An absent document means 'no manual tags exist' — the engine behaves
    exactly as pre-CR-023 (all sub_sector fallback). This is the documented
    backward-compatible semantic, not silent repair of a broken file.
    """
    p = Path(path or config.THEMES_PATH)
    return p.read_bytes() if p.exists() else None


def document_sha256(path=None):
    data = document_bytes(path)
    return hashlib.sha256(data).hexdigest() if data is not None else None


def empty_document() -> dict:
    return {"schema_version": SCHEMA_VERSION, "document_version": 0,
            "effective_from": None, "owner": None, "source": None,
            "change_id": None, "taxonomy": [], "assignments": []}


def load_theme_document(path=None) -> dict:
    data = document_bytes(path)
    if data is None:
        return empty_document()
    doc = yaml.safe_load(data.decode("utf-8"))
    return doc if isinstance(doc, dict) else {"_malformed": True}


def _iso_date(value):
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None


# ---- validation (strict, no silent repair) ------------------------------------


def validate_theme_document(doc: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["document must be a mapping"]
    for field in REQUIRED_DOC_FIELDS:
        if field not in doc:
            errors.append(f"document: missing required field {field!r}")
    if errors:
        return errors
    if doc.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"document: schema_version must be {SCHEMA_VERSION}")
    dv = doc.get("document_version")
    if not (isinstance(dv, int) and not isinstance(dv, bool) and dv >= 0):
        errors.append("document: document_version must be a non-negative integer")
    eff = doc.get("effective_from")
    if eff is not None and _iso_date(eff) is None:
        errors.append(f"document: effective_from {eff!r} is not an ISO date")
    for field in ("owner", "source", "change_id"):
        value = doc.get(field)
        if value is not None and not (isinstance(value, str) and value.strip()):
            errors.append(f"document: {field} must be a non-empty string")

    taxonomy = doc.get("taxonomy")
    if not isinstance(taxonomy, list):
        errors.append("document: taxonomy must be a list")
        taxonomy = []
    ids: set[str] = set()
    for i, entry in enumerate(taxonomy):
        if not isinstance(entry, dict):
            errors.append(f"taxonomy[{i}]: must be a mapping")
            continue
        for field in REQUIRED_TAXONOMY_FIELDS:
            if field not in entry:
                errors.append(f"taxonomy[{i}]: missing required field {field!r}")
        tid = entry.get("id")
        if tid is not None:
            if not (isinstance(tid, str) and tid.strip()):
                errors.append(f"taxonomy[{i}].id: must be a non-empty string")
            elif tid in ids:
                errors.append(f"taxonomy[{i}].id: duplicate theme id {tid!r}")
            else:
                ids.add(tid)

    assignments = doc.get("assignments") or []
    if not isinstance(assignments, list):
        errors.append("document: assignments must be a list")
        return errors
    seen: set[str] = set()
    for i, entry in enumerate(assignments):
        if not isinstance(entry, dict):
            errors.append(f"assignments[{i}]: must be a mapping")
            continue
        for field in REQUIRED_ASSIGNMENT_FIELDS:
            if field not in entry:
                errors.append(f"assignments[{i}]: missing provenance field {field!r}")
        inst = entry.get("instrument")
        if isinstance(inst, str) and inst.strip():
            if inst in seen:
                errors.append(
                    f"assignments[{i}]: duplicate assignment for instrument {inst!r} "
                    f"(exactly one manual theme per holding, H2-D8)")
            seen.add(inst)
        theme = entry.get("theme")
        if theme is not None and theme not in ids:
            errors.append(f"assignments[{i}].theme: {theme!r} is not in the taxonomy")
        if entry.get("effective_from") is not None and _iso_date(entry.get("effective_from")) is None:
            errors.append(f"assignments[{i}].effective_from must be an ISO date")
        if "rationale" in entry and entry["rationale"] is not None \
                and not isinstance(entry["rationale"], str):
            errors.append(f"assignments[{i}].rationale: must be a string when present")
        ver = entry.get("version")
        if ver is not None and not (isinstance(ver, int) and not isinstance(ver, bool) and ver > 0):
            errors.append(f"assignments[{i}].version must be a positive integer")
    return errors


def load_and_validate(path=None) -> dict:
    doc = load_theme_document(path)
    errors = validate_theme_document(doc)
    if errors:
        raise ValueError("theme mapping document invalid: " + "; ".join(errors))
    return doc


def validate_version_order(previous: dict, new: dict) -> list[str]:
    """Cross-version discipline (H2-D6/H2-D9): a new document supersedes the
    previous one only if it is strictly newer.

    Rules: strictly greater document_version; non-decreasing effective_from;
    theme IDs immutable; a changed theme name requires a rename_history entry
    referencing the previous name (historical labels are never mutated).
    """
    errors: list[str] = []
    pv, nv = previous.get("document_version", 0), new.get("document_version", 0)
    if isinstance(pv, int) and isinstance(nv, int) and nv <= pv:
        errors.append(f"version: new document_version {nv} must be > previous {pv}")
    pe, ne = _iso_date(previous.get("effective_from")), _iso_date(new.get("effective_from"))
    if pe and ne and ne < pe:
        errors.append(f"version: new effective_from {ne} must be >= previous {pe}")
    prev_by_id = {t["id"]: t for t in previous.get("taxonomy", []) if isinstance(t, dict)}
    for entry in new.get("taxonomy", []):
        if not isinstance(entry, dict):
            continue
        prior = prev_by_id.get(entry.get("id"))
        if prior and entry.get("name") != prior.get("name"):
            history = {h.get("name") for h in entry.get("rename_history", [])
                       if isinstance(h, dict)}
            if prior.get("name") not in history:
                errors.append(
                    f"theme {entry['id']}: renamed from {prior['name']!r} without a "
                    f"rename_history entry (H2-D9)")
    return errors


# ---- resolution (pure) ----------------------------------------------------------


def resolve_theme(doc: dict, instrument: str, as_of) -> str | None:
    """Manual theme ID for ``instrument`` at ``as_of``, else None (fallback).

    Effective-dated: the document applies only when its effective_from is
    on/before as_of; each assignment likewise. Exactly one assignment per
    instrument per document is guaranteed by validation.
    """
    run_date = as_of if isinstance(as_of, date) else date.fromisoformat(str(as_of))
    doc_eff = _iso_date(doc.get("effective_from"))
    if doc_eff is not None and doc_eff > run_date:
        return None
    for entry in doc.get("assignments") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("instrument") != instrument:
            continue
        a_eff = _iso_date(entry.get("effective_from"))
        if a_eff is not None and a_eff > run_date:
            continue
        return entry.get("theme")
    return None
