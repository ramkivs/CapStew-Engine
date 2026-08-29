"""CR-023 (EMM-H2) manual theme-tag layer — proof battery.

Maps 1:1 to the authority test requirements:

 1. Manual theme grouping                         -> test_manual_theme_grouping
 2. Fallback to sub_sector                        -> test_fallback_sub_sector_when_unmapped
 3. Manual precedence over sub_sector             -> test_manual_precedence_over_sub_sector
 4. >20% breach                                   -> test_breach_grouping_over_20
 5. exactly 20% is NOT a breach                   -> test_threshold_boundary_unit
 6. duplicate assignments rejected                -> test_duplicate_assignment_rejected
 7. unknown taxonomy values rejected              -> test_unknown_theme_rejected
 8. missing provenance rejected                   -> test_missing_provenance_rejected
 9. effective dating works                        -> test_effective_dating
10. version ordering works                        -> test_version_ordering
11. rename creates a new version                  -> test_rename_requires_history_new_version
12. historical run meaning preserved              -> test_historical_run_meaning_preserved
13. theme-document hash/integrity                 -> test_theme_document_integrity
14. archive linkage                               -> test_archive_linkage
15. deterministic replay                          -> test_deterministic_replay
16. concentration does not alter decisions        -> test_decisions_unchanged
17. concentration does not alter gates            -> test_gates_unchanged
18. concentration does not alter sizing           -> test_sizing_unchanged
19. concentration does not alter tax              -> test_tax_unchanged
20. concentration does not alter review cadence   -> test_review_cadence_unchanged

Plus: run-sample row pin for the shipped v1 document, distribution/enum
invariants, and _is_financial safety (sub_sector untouched).
"""
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app import archive, config
from app import themes as themes_mod
from app.determinism import content_hash
from app.main import app

ROOT = Path(__file__).resolve().parent.parent
FIXDIR = ROOT / "fixtures"
client = TestClient(app)
AS_OF = date(2026, 8, 22)


def _base_taxonomy():
    def t(tid, name):
        return {"id": tid, "name": name, "definition": f"def {tid}",
                "inclusion_rule": "in", "exclusion_rule": "out"}
    return [t("RATE_FIN", "Rate-sensitive financials"),
            t("PSU_GOV", "PSU / government-linked"),
            t("CAPEX_INFRA", "Capex / infrastructure"),
            t("CONSUMPTION", "Consumption"),
            t("PHARMA_HEALTH", "Pharma / healthcare"),
            t("IT_EXPORT", "IT / export services")]


def _assignment(instrument, theme, eff="2026-08-01", version=1, chg="chg-t", **extra):
    a = {"instrument": instrument, "theme": theme, "owner": "Ramki (authority)",
         "source": "synthetic test doc", "effective_from": eff,
         "version": version, "change_id": chg}
    a.update(extra)
    return a


def _doc_dict(assignments=(), version=1, eff="2026-08-01", taxonomy=None):
    return {"schema_version": 1, "document_version": version,
            "effective_from": eff, "owner": "Ramki (authority)",
            "source": "synthetic test doc", "change_id": f"chg-v{version}",
            "taxonomy": taxonomy if taxonomy is not None else _base_taxonomy(),
            "assignments": list(assignments)}


def _write_doc(tmp_path, doc):
    p = tmp_path / "themes.yaml"
    p.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
                 encoding="utf-8")
    return p


def _use(monkeypatch, path):
    monkeypatch.setattr(config, "THEMES_PATH", path)


def _run():
    from app.pipeline import decide_on_foundation, run_foundation
    f = run_foundation(FIXDIR / "portfolio.csv", FIXDIR / "screener.csv",
                       FIXDIR / "ledger.csv", as_of=AS_OF)
    return f, decide_on_foundation(f)


def _rows(payload):
    return {r["theme"]: r for r in payload["portfolio_layer"]["theme_concentration"]}


# --- 1/2/3/4/5: grouping, fallback, precedence, threshold ------------------------


def test_manual_theme_grouping(monkeypatch, tmp_path):
    doc = _doc_dict([
        _assignment("Salasar Techno Engg", "CAPEX_INFRA"),
        _assignment("Ashoka Buildcon", "CAPEX_INFRA"),
        _assignment("Bharat Coking Coal", "PSU_GOV"),
    ])
    _use(monkeypatch, _write_doc(tmp_path, doc))
    f, p = _run()
    pos = {x["instrument"]: x for x in f["positions"]}
    rows = _rows(p)
    assert rows["CAPEX_INFRA"]["source"] == "manual"
    assert rows["CAPEX_INFRA"]["alloc_pct"] == round(
        pos["Salasar Techno Engg"]["alloc_pct"] + pos["Ashoka Buildcon"]["alloc_pct"], 2)
    assert rows["PSU_GOV"]["source"] == "manual"
    assert rows["PSU_GOV"]["alloc_pct"] == round(pos["Bharat Coking Coal"]["alloc_pct"], 2)
    # the untouched members of the old sub_sector group stay in fallback form
    lt = pos["Larsen & Toubro"]
    assert rows["Engineering - Infrastructure"]["source"] == "fallback_sub_sector"
    assert rows["Engineering - Infrastructure"]["alloc_pct"] == round(lt["alloc_pct"], 2)
    assert "Mining" not in rows, "BCC's sub_sector group must dissolve once manually tagged"
    # position-level additive fields
    assert pos["Salasar Techno Engg"]["theme"] == "CAPEX_INFRA"
    assert pos["Salasar Techno Engg"]["theme_source"] == "manual"
    assert pos["Larsen & Toubro"]["theme_source"] == "fallback_sub_sector"
    # fundamentals.sub_sector intact
    assert pos["Salasar Techno Engg"]["fundamentals"]["sub_sector"] == \
        "Engineering - Infrastructure"


LINEAR_LEGACY = [
    ("Engineering - Infrastructure", 40.66, "breach"),
    ("Banks - Private", 20.6, "breach"),
    ("NBFC", 18.48, "ok"),
    ("Banks - PSU", 10.67, "ok"),
    ("Mining", 6.55, "ok"),
    ("Unknown", 2.0, "ok"),
    ("Capital Markets", 1.04, "ok"),
]


def test_fallback_sub_sector_when_unmapped():
    """Shipped v1 document (taxonomy only, zero assignments): concentration is
    byte-equivalent to the pre-CR-023 grouping, and every row is honestly
    labelled fallback_sub_sector."""
    _, p = _run()
    rows = p["portfolio_layer"]["theme_concentration"]
    assert [(r["theme"], r["alloc_pct"], r["status"]) for r in rows] == LINEAR_LEGACY
    assert all(r["source"] == "fallback_sub_sector" for r in rows)


def test_manual_precedence_over_sub_sector(monkeypatch, tmp_path):
    doc = _doc_dict([_assignment("HDFC Bank", "RATE_FIN"),
                     _assignment("Bank of Baroda", "RATE_FIN"),
                     _assignment("Bajaj Finance", "RATE_FIN")])
    _use(monkeypatch, _write_doc(tmp_path, doc))
    f, p = _run()
    pos = {x["instrument"]: x for x in f["positions"]}
    rows = _rows(p)
    rate = rows["RATE_FIN"]
    assert rate["source"] == "manual"
    expected = round(sum(pos[n]["alloc_pct"] for n in
                         ("HDFC Bank", "Bank of Baroda", "Bajaj Finance")), 2)
    assert rate["alloc_pct"] == expected
    for dissolved in ("Banks - Private", "Banks - PSU", "NBFC"):
        assert dissolved not in rows, \
            f"{dissolved}: manual tags win the grouping surface — its members left this row"


def test_breach_grouping_over_20(monkeypatch, tmp_path):
    doc = _doc_dict([_assignment("HDFC Bank", "RATE_FIN"),
                     _assignment("Bank of Baroda", "RATE_FIN"),
                     _assignment("Bajaj Finance", "RATE_FIN")])
    _use(monkeypatch, _write_doc(tmp_path, doc))
    _, p = _run()
    rate = _rows(p)["RATE_FIN"]
    assert rate["alloc_pct"] == 49.75 and rate["status"] == "breach", \
        ">20% must breach (authority-confirmed threshold, H2-D4-A)"


def test_threshold_boundary_unit():
    from app.decision import THEME_BREACH_THRESHOLD_PCT, _theme_status
    assert THEME_BREACH_THRESHOLD_PCT == 20.0, \
        "G-14 authority threshold is exactly 20% (H2-D4-A); no 15%, no bands"
    assert _theme_status(20.0) == "ok", "exactly 20% is NOT a breach"
    assert _theme_status(19.999) == "ok"
    assert _theme_status(20.001) == "breach"
    assert _theme_status(49.75) == "breach"


# --- 6/7/8: strict validation -----------------------------------------------------


def test_duplicate_assignment_rejected():
    doc = _doc_dict([_assignment("Salasar Techno Engg", "CAPEX_INFRA"),
                     _assignment("Salasar Techno Engg", "PSU_GOV", chg="chg-t2")])
    errors = themes_mod.validate_theme_document(doc)
    assert any("duplicate assignment" in e and "Salasar Techno Engg" in e for e in errors)


def test_unknown_theme_rejected():
    doc = _doc_dict([_assignment("Salasar Techno Engg", "NOT_A_THEME")])
    errors = themes_mod.validate_theme_document(doc)
    assert any("NOT_A_THEME" in e and "not in the taxonomy" in e for e in errors)


def test_missing_provenance_rejected():
    a = {"instrument": "Salasar Techno Engg", "theme": "CAPEX_INFRA"}
    doc = _doc_dict([a])
    errors = themes_mod.validate_theme_document(doc)
    for field in ("owner", "source", "effective_from", "version", "change_id"):
        assert any(field in e and "provenance" in e for e in errors), \
            f"missing provenance field {field} must be reported"


def test_invalid_document_blocks_run(monkeypatch, tmp_path):
    doc = _doc_dict([_assignment("Salasar Techno Engg", "NOPE")])
    _use(monkeypatch, _write_doc(tmp_path, doc))
    with pytest.raises(ValueError, match="theme mapping document invalid"):
        _run()


# --- 9/10/11: effective dating, ordering, rename -----------------------------------


def test_effective_dating(monkeypatch, tmp_path):
    # assignment effective AFTER the run as_of => not applied
    doc = _doc_dict([_assignment("HDFC Bank", "RATE_FIN", eff="2026-08-23")],
                    eff="2026-08-01")
    _use(monkeypatch, _write_doc(tmp_path, doc))
    f, p = _run()
    pos = {x["instrument"]: x for x in f["positions"]}
    assert pos["HDFC Bank"]["theme_source"] == "fallback_sub_sector"
    # document effective AFTER the run as_of => the whole document is inert
    doc["effective_from"] = "2026-09-01"
    _use(monkeypatch, _write_doc(tmp_path, doc))
    f, p = _run()
    assert all(pos_["theme_source"] == "fallback_sub_sector" for pos_ in f["positions"])
    # assignment effective ON the as_of boundary => applied
    doc = _doc_dict([_assignment("HDFC Bank", "RATE_FIN", eff="2026-08-22")],
                    eff="2026-08-01")
    _use(monkeypatch, _write_doc(tmp_path, doc))
    f, p = _run()
    pos = {x["instrument"]: x for x in f["positions"]}
    assert pos["HDFC Bank"]["theme"] == "RATE_FIN"
    assert pos["HDFC Bank"]["theme_source"] == "manual"


def test_version_ordering():
    prev = _doc_dict(version=1, eff="2026-08-01")
    ok_next = _doc_dict(version=2, eff="2026-09-01")
    assert themes_mod.validate_version_order(prev, ok_next) == []
    same_version = _doc_dict(version=1, eff="2026-09-01")
    errors = themes_mod.validate_version_order(prev, same_version)
    assert any("must be >" in e for e in errors)
    earlier_eff = _doc_dict(version=2, eff="2026-07-01")
    errors = themes_mod.validate_version_order(prev, earlier_eff)
    assert any("effective_from" in e for e in errors)


def test_rename_requires_history_new_version():
    prev = _doc_dict(version=1, eff="2026-08-01")
    renamed = _doc_dict(version=2, eff="2026-09-01")
    renamed["taxonomy"][2]["name"] = "Capex / Defence & Infra"   # id CAPEX_INFRA
    errors = themes_mod.validate_version_order(prev, renamed)
    assert any("CAPEX_INFRA" in e and "rename_history" in e for e in errors)
    renamed["taxonomy"][2]["rename_history"] = [
        {"name": "Capex / infrastructure", "until_version": 1}]
    assert themes_mod.validate_version_order(prev, renamed) == [], \
        "a rename with rename_history at a strictly newer version is the legal path (H2-D9)"


def test_historical_run_meaning_preserved(monkeypatch, tmp_path):
    doc1 = _doc_dict([_assignment("Salasar Techno Engg", "CAPEX_INFRA")], version=1,
                     eff="2026-08-01")
    _use(monkeypatch, _write_doc(tmp_path, doc1))
    resp_a = client.post("/api/v1/run-sample")
    assert resp_a.status_code == 200, resp_a.text
    payload_a = resp_a.json()
    names_a = {r["theme"] for r in payload_a["portfolio_layer"]["theme_concentration"]}
    assert "CAPEX_INFRA" in names_a
    e1 = payload_a["engine_version"]

    doc2 = _doc_dict([_assignment("Salasar Techno Engg", "CAPEX_INFRA")], version=2,
                     eff="2026-09-01")
    doc2["taxonomy"][2]["name"] = "Capex / Defence & Infra"
    doc2["taxonomy"][2]["rename_history"] = [
        {"name": "Capex / infrastructure", "until_version": 1}]
    _use(monkeypatch, _write_doc(tmp_path, doc2))
    resp_b = client.post("/api/v1/run-sample")
    assert resp_b.status_code == 200, resp_b.text

    stored_a = client.get(f"/api/v1/decisions?run_id={payload_a['run_id']}").json()
    names_stored_a = {r["theme"] for r in
                      stored_a["portfolio_layer"]["theme_concentration"]}
    assert "CAPEX_INFRA" in names_stored_a, \
        "historical runs retain the theme meaning that existed at their run time"
    assert e1 == stored_a["engine_version"]
    assert themes_mod.validate_version_order(doc1, doc2) == []


# --- 13/14/15: integrity, linkage, replay -------------------------------------------


def test_theme_document_integrity():
    client.post("/api/v1/run-sample")
    shipped_sha = hashlib.sha256(
        (ROOT / "themes" / "themes.yaml").read_bytes()).hexdigest()
    blob = archive.blob_path_for(shipped_sha)
    assert blob.exists(), "authority document bytes must be archived (content-addressed)"
    assert blob.read_bytes() == (ROOT / "themes" / "themes.yaml").read_bytes()
    data = bytearray(blob.read_bytes())
    data[0] ^= 0xFF
    blob.write_bytes(bytes(data))
    result = archive.verify()
    assert result["ok"] is False
    assert any("blob content mismatch" in e for e in result["errors"])


def test_archive_linkage():
    resp = client.post("/api/v1/run-sample")
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    entries = [e for e in archive.run_entries(payload["run_id"]) if e["kind"] == "ingest"]
    assert len(entries) == 1
    entry = entries[0]
    rec = next(f for f in entry["files"] if f["slot"] == "themes_document")
    assert rec["filename"] == "themes.yaml"
    assert rec["as_of_source"] == "authority_document"
    assert rec["declared_source_as_of"] == "2026-08-29"   # shipped doc effective_from
    assert rec["parse_status"] == "validated"
    assert rec["sha256"] == hashlib.sha256(
        (ROOT / "themes" / "themes.yaml").read_bytes()).hexdigest()
    assert payload["provenance"]["archive"]["themes_sha256"] == rec["sha256"]
    assert archive.verify()["ok"] is True


def test_deterministic_replay(monkeypatch, tmp_path):
    doc = _doc_dict([_assignment("HDFC Bank", "RATE_FIN")])
    _use(monkeypatch, _write_doc(tmp_path, doc))
    f1, p1 = _run()
    f2, p2 = _run()
    assert f1["content_hash"] == f2["content_hash"]
    assert p1["content_hash"] == p2["content_hash"]

    from app.pipeline import decide_on_foundation
    entry = [e for e in archive.run_entries(f1["run_id"]) if e["kind"] == "ingest"][0]
    corpus = json.loads(archive.read_blob(entry["foundation_sha256"]).decode("utf-8"))
    themes_sha = next(x["sha256"] for x in entry["files"]
                      if x["slot"] == "themes_document")
    rebuilt = {k: v for k, v in corpus.items() if k != "archive_blob_kind"}
    rebuilt["provenance"]["archive"] = archive.archive_identity(
        entry["foundation_sha256"], entry["policy_sha256"], themes_sha256=themes_sha)
    rebuilt["run_id"] = "replay"
    rebuilt["content_hash"] = content_hash(
        {k: v for k, v in rebuilt.items() if k != "run_id"})
    assert rebuilt["content_hash"] == f1["content_hash"]
    replayed = decide_on_foundation(rebuilt)
    assert replayed["content_hash"] == p1["content_hash"], \
        "replay via the archived corpus + archived theme document reproduces the run"


# --- 16–20: functional invariants (manual tags touch ONLY the grouping surface) -------


def _invariant_pair(monkeypatch, tmp_path):
    """(empty-doc run) vs (fully-tagged run) on identical fixture inputs."""
    from app.pipeline import decide_on_foundation, run_foundation
    _, p_empty = _run()
    doc = _doc_dict([
        _assignment("HDFC Bank", "RATE_FIN"), _assignment("Bajaj Finance", "RATE_FIN"),
        _assignment("Bank of Baroda", "RATE_FIN"), _assignment("Salasar Techno Engg", "CAPEX_INFRA"),
        _assignment("Ashoka Buildcon", "CAPEX_INFRA"), _assignment("Larsen & Toubro", "CAPEX_INFRA"),
        _assignment("Bharat Coking Coal", "PSU_GOV"), _assignment("DAM Capital Advisors", "PSU_GOV"),
        _assignment("AGI Greenpac", "CONSUMPTION"),
    ])
    _use(monkeypatch, _write_doc(tmp_path, doc))
    _, p_tagged = _run()
    empty_by = {h["instrument"]: h for h in p_empty["holdings"]}
    tagged_by = {h["instrument"]: h for h in p_tagged["holdings"]}
    assert set(empty_by) == set(tagged_by)
    return p_empty, p_tagged, empty_by, tagged_by


def test_decisions_unchanged(monkeypatch, tmp_path):
    p_empty, p_tagged, e, t = _invariant_pair(monkeypatch, tmp_path)
    for inst in e:
        for field in ("decision", "composite_score", "confidence",
                      "subscores", "reason_tree"):
            assert e[inst][field] == t[inst][field], \
                f"{inst}.{field} must not move when only concentration grouping changes"
    assert p_empty["portfolio_summary"]["decision_distribution"] == \
        p_tagged["portfolio_summary"]["decision_distribution"]
    from app.schema import DECISIONS
    assert DECISIONS == {"HOLD", "WATCH", "TRIM", "HARVEST", "EXIT", "NO-DECISION"}


def test_gates_unchanged(monkeypatch, tmp_path):
    _, _, e, t = _invariant_pair(monkeypatch, tmp_path)
    for inst in e:
        assert e[inst]["stage1"] == t[inst]["stage1"], \
            f"{inst}: stage1 gates (incl. gates_fired) must not move"


def test_sizing_unchanged(monkeypatch, tmp_path):
    _, _, e, t = _invariant_pair(monkeypatch, tmp_path)
    for inst in e:
        assert e[inst]["subscores"]["position_sizing"] == t[inst]["subscores"]["position_sizing"]
        assert e[inst]["trim"] == t[inst]["trim"], f"{inst}: trim sizing must not move"
        assert e[inst]["alloc_pct"] == t[inst]["alloc_pct"]


def test_tax_unchanged(monkeypatch, tmp_path):
    p_empty, p_tagged, e, t = _invariant_pair(monkeypatch, tmp_path)
    for inst in e:
        assert e[inst]["tax_status"] == t[inst]["tax_status"], f"{inst}: tax status must not move"
    assert p_empty["portfolio_summary"]["tax"] == p_tagged["portfolio_summary"]["tax"]
    assert p_empty["portfolio_layer"]["tax_sequencing"] == \
        p_tagged["portfolio_layer"]["tax_sequencing"]


def test_review_cadence_unchanged(monkeypatch, tmp_path):
    _, _, e, t = _invariant_pair(monkeypatch, tmp_path)
    for inst in e:
        assert e[inst]["next_review_date"] == t[inst]["next_review_date"], \
            f"{inst}: review cadence (D-15) must not move"


# --- safety: sub_sector stays global -----------------------------------------------


def test_is_financial_still_uses_sub_sector(monkeypatch, tmp_path):
    """Assigning a manual tag must not disturb the financial-name scoring rule
    (quality_drift skips ROCE/debt penalties for banks/NBFCs via sub_sector)."""
    from app.scoring import quality_drift
    sample = {"sub_sector": "NBFC", "roe": 12.0, "roce": 1.0, "debt_equity": 9.0}
    assert quality_drift(sample) == 0.0, "_is_financial exemption must remain on sub_sector"
    p_empty, p_tagged, e, t = _invariant_pair(monkeypatch, tmp_path)
    for inst in e:
        assert e[inst]["subscores"]["quality_drift"] == t[inst]["subscores"]["quality_drift"], \
            f"{inst}: quality drift must not move with a manual tag assigned"
