"""CR-022 (EMM-F2) snapshot archiver / dated fundamentals store — proof battery.

Maps 1:1 to the authority validation requirements:

 1. raw source bytes are archived                    -> test_raw_bytes_archived
 2. raw SHA-256 is stable                            -> test_raw_sha256_stable
 3. normalized FoundationPayload is archived         -> test_normalized_foundation_archived
 4. archive manifest links to the run                -> test_manifest_links_run
 5. policy snapshot is retained                      -> test_policy_snapshot_retained
 6. archive version is recorded                      -> test_archive_version_recorded
 7. replay from archived normalized input == result  -> test_replay_from_archived_foundation
 8. tampering with a blob/manifest is detected       -> test_tamper_blob/_manifest/_chain
 9. repeated identical input: no silent mutation     -> test_repeated_identical_input
10. distinct source replacements: distinct identity  -> test_distinct_source_replacement
11. existing run-history behavior unchanged          -> test_run_history_unchanged
12. G-04 remains explicitly proxy-labelled           -> test_g04_proxy_labels_preserved
13. G-05 remains open                                -> test_g05_remains_open
14. no decision-state/taxonomy behavior changes      -> test_taxonomy_unchanged

Plus F2-D3 dual-timestamp semantics, the pre-parse capture guarantee (D10.2),
and the what-if non-persistence guard.
"""
import hashlib
import inspect
import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import archive, config
from app.determinism import content_hash
from app.main import app

ROOT = Path(__file__).resolve().parent.parent
FIXDIR = ROOT / "fixtures"
client = TestClient(app)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_run(tmp_path=None):
    """POST /run-sample and return its payload (archive+store isolated by conftest)."""
    resp = client.post("/api/v1/run-sample")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ingest_entry(run_id):
    entries = [e for e in archive.run_entries(run_id) if e["kind"] == "ingest"]
    assert len(entries) == 1, f"expected exactly one ingest entry for {run_id}"
    return entries[0]


def _slot_record(entry, slot):
    return next(f for f in entry["files"] if f["slot"] == slot)


# --- 1/2/3/5: capture, retention -----------------------------------------------


def test_raw_bytes_archived():
    payload = _fixture_run()
    entry = _ingest_entry(payload["run_id"])
    for slot, fixture in (("portfolio", "portfolio.csv"),
                          ("screener", "screener.csv"),
                          ("ledger", "ledger.csv")):
        rec = _slot_record(entry, slot)
        src = FIXDIR / fixture
        assert rec["filename"] == fixture
        assert rec["sha256"] == _sha(src), f"{slot}: raw sha must be sha256 of the file bytes"
        assert rec["size_bytes"] == src.stat().st_size
        assert rec["parse_status"] == "ok"
        blob = archive.blob_path_for(rec["sha256"])
        assert blob.exists(), f"{slot}: blob missing at {blob}"
        assert blob.read_bytes() == src.read_bytes(), f"{slot}: archived bytes must be byte-identical"
        assert rec["blob"] == archive.blob_relpath(rec["sha256"])
        assert rec["rows"] is not None and rec["rows"] > 0
        assert "ingested_at" in rec  # per-file wall-clock receipt timestamp (F2-D3)
        assert "declared_source_as_of" in rec and "as_of_source" in rec


def test_raw_sha256_stable_across_runs():
    expected = {slot: _sha(FIXDIR / f"{slot}.csv")
                for slot in ("portfolio", "screener", "ledger")}
    # CR-023: the ingest record also captures the authority theme document.
    expected["themes_document"] = hashlib.sha256(
        (ROOT / "themes" / "themes.yaml").read_bytes()).hexdigest()
    for _ in range(2):
        payload = _fixture_run()
        entry = _ingest_entry(payload["run_id"])
        got = {f["slot"]: f["sha256"] for f in entry["files"]}
        assert got == expected, "raw SHA-256 must be identical for identical inputs across runs"


def test_normalized_foundation_archived():
    payload = _fixture_run()
    entry = _ingest_entry(payload["run_id"])
    fsha = entry["foundation_sha256"]
    blob = archive.blob_path_for(fsha)
    assert blob.exists() and entry["foundation_blob"] == archive.blob_relpath(fsha)
    assert hashlib.sha256(blob.read_bytes()).hexdigest() == fsha
    corpus = json.loads(blob.read_bytes().decode("utf-8"))
    assert corpus["archive_blob_kind"] == "foundation"
    # The corpus is the decision-relevant normalized input, with no hashes and
    # no identity fields inside it (no self-reference cycle).
    assert "content_hash" not in corpus and "run_id" not in corpus
    for key in ("as_of", "data_as_of", "provenance", "reconciliation",
                "positions", "lots", "warnings"):
        assert key in corpus, f"corpus missing {key}"
    assert len(corpus["positions"]) == 9  # fixture universe
    assert "archive" not in corpus["provenance"]
    # Canonical-serialization stability: re-serializing the parsed corpus must
    # reproduce the archived bytes exactly (hash stability, F2-D5).
    assert archive.foundation_blob_bytes(corpus) == blob.read_bytes()
    # The input hash of the persisted run reconstructs from the corpus alone.
    # CR-023: the block also carries the authority theme-document hash.
    themes_sha = _slot_record(entry, "themes_document")["sha256"]
    rebuilt = {k: v for k, v in corpus.items() if k != "archive_blob_kind"}
    rebuilt["provenance"]["archive"] = archive.archive_identity(
        entry["foundation_sha256"], entry["policy_sha256"],
        themes_sha256=themes_sha)
    assert content_hash(rebuilt) == payload["input_hash"]


def test_policy_snapshot_retained():
    payload = _fixture_run()
    entry = _ingest_entry(payload["run_id"])
    policy = config.POLICY_PATH
    assert entry["policy_sha256"] == _sha(policy)
    assert entry["policy_blob"] == archive.blob_relpath(entry["policy_sha256"])
    blob = archive.blob_path_for(entry["policy_sha256"])
    assert blob.exists() and blob.read_bytes() == policy.read_bytes()
    assert entry["policy_version"] == payload["policy_version"]


# --- 4/6: linkage, versions ------------------------------------------------------


def test_manifest_links_run():
    payload = _fixture_run()
    entry = _ingest_entry(payload["run_id"])
    assert entry["run_id"] == payload["run_id"]
    assert entry["input_hash"] == payload["input_hash"]
    assert entry["run_as_of"] == payload["as_of"]
    links = [e for e in archive.run_entries(payload["run_id"]) if e["kind"] == "run_link"]
    assert len(links) == 1
    assert links[0]["decision_content_hash"] == payload["content_hash"]
    assert links[0]["input_hash"] == payload["input_hash"]
    # Payload-visible provenance identifies manifest + archive integrity hashes.
    prov = payload["provenance"]["archive"]
    assert prov["manifest"] == archive.MANIFEST_NAME
    assert prov["foundation_sha256"] == entry["foundation_sha256"]
    assert prov["policy_sha256"] == entry["policy_sha256"]
    # CR-023: authority theme-document hash is linked too.
    assert prov["themes_sha256"] == _slot_record(entry, "themes_document")["sha256"]


def test_archive_version_recorded():
    payload = _fixture_run()
    assert config.ARCHIVE_VERSION == 1
    assert payload["provenance"]["archive"]["archive_version"] == 1
    for entry in archive.read_manifest():
        assert entry["archive_version"] == 1
    # VP-1: payload-visible provenance changed => ENGINE_VERSION bumped
    # (CR-022 0.4.0; CR-023 theme layer -> 0.5.0); calculation/normalization
    # lineage untouched (no math/normalizer change).
    assert config.ENGINE_VERSION == "0.5.0-phase3"
    assert payload["engine_version"] == "0.5.0-phase3"
    assert payload["provenance"]["engine_version"] == "0.5.0-phase3"
    assert config.CALCULATION_VERSION == "2.1"
    assert config.NORMALIZATION_VERSION == "1.0"


def test_sold_slot_joins_archive_lineage():
    readme = lambda n: (FIXDIR / n).read_bytes()
    files = [
        ("portfolio", ("portfolio.csv", readme("portfolio.csv"), "text/csv")),
        ("screener", ("screener.csv", readme("screener.csv"), "text/csv")),
        ("ledger", ("ledger.csv", readme("ledger.csv"), "text/csv")),
        ("sold", ("sold_sample.csv", readme("sold_sample.csv"), "text/csv")),
    ]
    resp = client.post("/api/v1/run", files=files)
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    slots = [e for e in archive.run_entries(payload["run_id"]) if e["kind"] == "slot"]
    assert len(slots) == 1
    rec = slots[0]["file"]
    assert rec["slot"] == "sold" and rec["filename"] == "sold_sample.csv"
    assert rec["sha256"] == _sha(FIXDIR / "sold_sample.csv")
    assert rec["parse_status"] == "ok" and rec["rows"] > 0
    assert archive.blob_path_for(rec["sha256"]).read_bytes() == (FIXDIR / "sold_sample.csv").read_bytes()
    assert payload["portfolio_summary"]["tax"]["provisional"] is False


# --- 7: replay equivalence -------------------------------------------------------


def test_replay_from_archived_foundation_produces_identical_result():
    from app.pipeline import decide_on_foundation, run_foundation

    foundation = run_foundation(FIXDIR / "portfolio.csv", FIXDIR / "screener.csv",
                                FIXDIR / "ledger.csv", as_of=date(2026, 8, 22))
    original = decide_on_foundation(foundation)

    entry = _ingest_entry(foundation["run_id"])
    corpus = json.loads(archive.read_blob(entry["foundation_sha256"]).decode("utf-8"))
    themes_sha = _slot_record(entry, "themes_document")["sha256"]
    rebuilt = {k: v for k, v in corpus.items() if k != "archive_blob_kind"}
    rebuilt["provenance"]["archive"] = archive.archive_identity(
        entry["foundation_sha256"], entry["policy_sha256"],
        themes_sha256=themes_sha)
    rebuilt["run_id"] = "replay_does_not_matter"
    rebuilt["content_hash"] = content_hash(
        {k: v for k, v in rebuilt.items() if k != "run_id"})
    assert rebuilt["content_hash"] == foundation["content_hash"], \
        "archived corpus must re-derive the original input hash"

    replayed = decide_on_foundation(rebuilt)
    assert replayed["content_hash"] == original["content_hash"], \
        "replay from archived normalized input must reproduce the engine result hash"
    assert replayed["input_hash"] == original["input_hash"]


# --- 8: tamper detection ---------------------------------------------------------


def _flip_first_byte(path: Path):
    data = bytearray(path.read_bytes())
    data[0] ^= 0xFF
    path.write_bytes(bytes(data))


def test_tamper_blob_detected():
    payload = _fixture_run()
    entry = _ingest_entry(payload["run_id"])
    assert archive.verify()["ok"] is True
    rec = _slot_record(entry, "portfolio")
    _flip_first_byte(archive.blob_path_for(rec["sha256"]))
    result = archive.verify()
    assert result["ok"] is False
    assert any("blob content mismatch" in e or "referenced blob missing" in e
               for e in result["errors"])


def test_tamper_manifest_body_detected():
    payload = _fixture_run()
    _ingest_entry(payload["run_id"])
    path = archive.manifest_path()
    lines = path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    entry["policy_version"] = 99  # silent history edit
    lines[0] = json.dumps(entry, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = archive.verify()
    assert result["ok"] is False
    assert any("entry_hash mismatch" in e for e in result["errors"])


def test_tamper_manifest_chain_break_detected():
    _fixture_run()
    _fixture_run()  # 4 entries: ingest, run_link, ingest, run_link
    lines = archive.manifest_path().read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4
    # Mid-chain removal: drop entry index 2 and re-seal nothing.
    kept = lines[:2] + lines[3:]
    archive.manifest_path().write_text("\n".join(kept) + "\n", encoding="utf-8")
    result = archive.verify()
    assert result["ok"] is False
    assert any("prev_entry_hash chain break" in e for e in result["errors"])


def test_tamper_manifest_reorder_detected():
    _fixture_run()  # 2 entries
    lines = archive.manifest_path().read_text(encoding="utf-8").splitlines()
    archive.manifest_path().write_text("\n".join([lines[1], lines[0]]) + "\n",
                                       encoding="utf-8")
    result = archive.verify()
    assert result["ok"] is False
    assert any("seq" in e or "chain break" in e for e in result["errors"])


# --- 9/10: event identity --------------------------------------------------------


def _all_blobs():
    d = Path(config.ARCHIVE_ROOT) / archive.BLOB_DIR_NAME
    return {p.relative_to(d).as_posix(): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


def test_repeated_identical_input_does_not_mutate_archive():
    _fixture_run()
    blobs_after_first = _all_blobs()
    entries_after_first = len(archive.read_manifest())
    _fixture_run()  # identical inputs, second event
    blobs_after_second = _all_blobs()
    assert blobs_after_second.keys() == blobs_after_first.keys(), \
        "identical bytes must map to identical blob identities (no duplicates)"
    for key, data in blobs_after_first.items():
        assert blobs_after_second[key] == data, \
            f"blob {key} silently mutated by a repeated identical ingestion"
    assert len(archive.read_manifest()) == entries_after_first + 2, \
        "repeat ingestion appends a NEW event without touching existing entries"
    assert archive.verify()["ok"] is True


def test_distinct_source_replacement_distinct_identity(tmp_path):
    from app.pipeline import run_foundation

    def copy_trio(dst: Path):
        dst.mkdir(exist_ok=True)
        for name in ("portfolio.csv", "screener.csv", "ledger.csv"):
            (dst / name).write_bytes((FIXDIR / name).read_bytes())

    # (a) byte-level replacement of the screener (trailing newline): raw archive
    # identity changes even though the parsed logical input is unchanged.
    a = tmp_path / "a"
    copy_trio(a)
    fa = run_foundation(a / "portfolio.csv", a / "screener.csv", a / "ledger.csv",
                        as_of=date(2026, 8, 22))
    b = tmp_path / "b"
    copy_trio(b)
    (b / "screener.csv").write_bytes((FIXDIR / "screener.csv").read_bytes() + b"\r\n")
    fb = run_foundation(b / "portfolio.csv", b / "screener.csv", b / "ledger.csv",
                        as_of=date(2026, 8, 22))
    sa = _slot_record(_ingest_entry(fa["run_id"]), "screener")["sha256"]
    sb = _slot_record(_ingest_entry(fb["run_id"]), "screener")["sha256"]
    assert sa != sb, "replaced bytes must receive a distinct archive identity"
    assert archive.blob_path_for(sa).exists() and archive.blob_path_for(sb).exists(), \
        "the original blob must remain untouched alongside its replacement"
    assert fa["content_hash"] == fb["content_hash"], \
        "byte-level replacement with identical logical input keeps the input hash"

    # (b) content-level replacement (market cap 3500 -> 3501): logical identity
    # and input hash both change.
    c = tmp_path / "c"
    copy_trio(c)
    text = (FIXDIR / "screener.csv").read_text(encoding="utf-8")
    assert text.count(",3500,146.15,") == 1
    (c / "screener.csv").write_text(text.replace(",3500,146.15,", ",3501,146.15,"),
                                    encoding="utf-8")
    fc = run_foundation(c / "portfolio.csv", c / "screener.csv", c / "ledger.csv",
                        as_of=date(2026, 8, 22))
    sc = _slot_record(_ingest_entry(fc["run_id"]), "screener")["sha256"]
    assert sc != sa
    assert fc["content_hash"] != fa["content_hash"]
    assert fc["provenance"]["archive"]["foundation_sha256"] != \
        fa["provenance"]["archive"]["foundation_sha256"]


# --- 11/12/13/14: regression invariants ------------------------------------------


LIST_RUN_KEYS = {"run_id", "as_of", "engine_version", "policy_version",
                 "input_hash", "content_hash", "created_at"}
DIFF_KEYS = {"run_id", "previous_run_id", "as_of", "changed",
             "removed_holdings", "distribution"}
SIX_STATES = {"HOLD", "WATCH", "TRIM", "HARVEST", "EXIT", "NO-DECISION"}


def test_run_history_behavior_unchanged():
    first = _fixture_run()
    second = _fixture_run()
    runs = client.get("/api/v1/runs").json()
    assert len(runs) == 2
    for row in runs:
        assert set(row.keys()) == LIST_RUN_KEYS, "runs listing columns must not change"
    diff = client.get(f"/api/v1/runs/{second['run_id']}/diff").json()
    assert set(diff.keys()) == DIFF_KEYS, "run diff shape must not change"
    assert diff["previous_run_id"] == first["run_id"]
    stored = client.get(f"/api/v1/decisions?run_id={second['run_id']}").json()
    assert stored["content_hash"] == second["content_hash"]
    assert stored["provenance"]["archive"] == second["provenance"]["archive"]


def test_g04_proxy_labels_preserved():
    """G-04 (own-5yr PE/PB median absent) stays a disclosed PROXY: valuation
    keeps scoring on peer-relative premiums; data_quality keeps saying 'proxy';
    no own-history conversion appears. F2-D8."""
    payload = _fixture_run()
    src = inspect.getsource(__import__("app.scoring", fromlist=["x"]))
    assert "pe_premium_vs_subsector" in src and "pb_premium_vs_subsector" in src
    assert "Own-5yr-median is a gap (proxy)" in src
    labelled_proxy = set()
    for h in payload["holdings"]:
        if h["decision"] == "NO-DECISION":
            continue
        label = h["data_quality"]["valuation_stretch"]
        assert label in ("proxy", "missing", "stale"), \
            f"{h['instrument']}: G-04 valuation must never be upgraded to " \
            f"'authoritative' (own-history median still absent)"
        if label == "proxy":
            labelled_proxy.add(h["instrument"])
    assert "Salasar Techno Engg" in labelled_proxy, \
        "in-universe valuations must stay explicitly proxy-labelled (F2-D8)"


def test_g05_remains_open_and_g1_history_legs_unfed():
    """F2-D9 + EMM-F2/G1-HIST: no quality time series is computed or consumed;
    G1 quality-drop / pledge-QoQ history legs stay silent (source-dependent)."""
    payload = _fixture_run()
    blob = inspect.getsource(__import__("app.gates", fromlist=["x"]))
    scoring = inspect.getsource(__import__("app.scoring", fromlist=["x"]))
    for forbidden in ("quality_drop", "pledge_qoq", "quality_series"):
        assert forbidden not in blob and forbidden not in scoring
    for h in payload["holdings"]:
        assert "quality_series" not in h and "quality_history" not in h


def test_taxonomy_and_distribution_unchanged():
    from app.schema import DECISIONS
    assert DECISIONS == SIX_STATES
    payload = _fixture_run()
    dist = payload["portfolio_summary"]["decision_distribution"]
    assert set(dist.keys()) <= SIX_STATES
    assert sum(dist.values()) == payload["portfolio_summary"]["holdings_count"] == 9
    assert dist == {"TRIM": 4, "EXIT": 1, "HOLD": 1, "WATCH": 3}, \
        "fixture distribution pinned by the certified suite must not move"


# --- F2-D3: dual-timestamp semantics ----------------------------------------------


def test_filename_declared_date_wins_over_mtime(tmp_path):
    from app.pipeline import run_foundation
    (tmp_path / "TT_mystockholdings_26_08_2026.csv").write_bytes(
        (FIXDIR / "portfolio.csv").read_bytes())
    (tmp_path / "screener.csv").write_bytes((FIXDIR / "screener.csv").read_bytes())
    (tmp_path / "ledger.csv").write_bytes((FIXDIR / "ledger.csv").read_bytes())
    f = run_foundation(tmp_path / "TT_mystockholdings_26_08_2026.csv",
                       tmp_path / "screener.csv", tmp_path / "ledger.csv",
                       as_of=date(2026, 8, 27))
    src = f["provenance"]["sources"]["portfolio"]
    assert src["as_of"] == "2026-08-26"
    assert src["declared_source_as_of"] == "2026-08-26"
    assert src["as_of_source"] == "declared_filename"
    for slot in ("screener", "ledger"):
        assert f["provenance"]["sources"][slot]["as_of_source"] == "fallback_upload_mtime"
        assert f["provenance"]["sources"][slot]["declared_source_as_of"] is None
    # the declared date (not the upload mtime) feeds the data-age bookkeeping
    assert f["data_as_of"]["portfolio"] == "2026-08-26"


def test_explicit_declaration_wins_and_drives_staleness(tmp_path):
    from app.pipeline import run_foundation
    for name in ("portfolio.csv", "screener.csv", "ledger.csv"):
        (tmp_path / name).write_bytes((FIXDIR / name).read_bytes())
    f = run_foundation(tmp_path / "portfolio.csv", tmp_path / "screener.csv",
                       tmp_path / "ledger.csv", as_of=date(2026, 8, 22),
                       declared_as_of={"ledger": "2026-08-01"})
    src = f["provenance"]["sources"]["ledger"]
    assert src["as_of"] == "2026-08-01"
    assert src["as_of_source"] == "declared_explicit"
    assert src["declared_source_as_of"] == "2026-08-01"
    # Staleness thresholds UNCHANGED (7d ledger / 3d valuation) — only the
    # data-age input is corrected: 21 days behind => STALENESS fires.
    assert config.STALENESS_DAYS_LEDGER == 7 and config.STALENESS_DAYS_VALUATION == 3
    assert "ledger" in f["data_as_of"]["stale_files"]
    assert any(w["code"] == "STALENESS" and w["message"].startswith("ledger is ")
               for w in f["warnings"])


def test_declared_date_precedence_and_fallback_asset_labels():
    from app.pipeline import declared_as_of_from_filename, resolve_slot_as_of
    assert declared_as_of_from_filename("TT_mystockholdings_26_08_2026.csv") == date(2026, 8, 26)
    assert declared_as_of_from_filename("xirr_report_2026-08-26.csv") == date(2026, 8, 26)
    assert declared_as_of_from_filename("RAW TRADE LEDGER.csv") is None
    assert declared_as_of_from_filename("mystockholdings_2026_13_40.csv") is None
    r = resolve_slot_as_of("portfolio", FIXDIR / "portfolio.csv",
                           {"portfolio": "2026-08-20"})
    assert r["as_of_source"] == "declared_explicit" and r["as_of"] == "2026-08-20"
    with pytest.raises(ValueError):
        resolve_slot_as_of("portfolio", FIXDIR / "portfolio.csv",
                           {"portfolio": "26-08-2026"})  # not ISO => rejected
    f = resolve_slot_as_of("portfolio", FIXDIR / "portfolio.csv", None)
    assert f["as_of_source"] == "fallback_upload_mtime"
    assert f["declared_source_as_of"] is None


def test_ingest_endpoint_accepts_declared_dates_and_labels():
    data = {"portfolio_as_of": "2026-08-20"}
    with open(FIXDIR / "portfolio.csv", "rb") as pf, \
         open(FIXDIR / "screener.csv", "rb") as sf, \
         open(FIXDIR / "ledger.csv", "rb") as lf:
        resp = client.post("/api/v1/ingest", files=[
            ("portfolio", ("TT_mystockholdings.csv", pf.read(), "text/csv")),
            ("screener", ("screener.csv", sf.read(), "text/csv")),
            ("ledger", ("ledger.csv", lf.read(), "text/csv")),
        ], data=data)
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["provenance"]["sources"]["portfolio"]["as_of_source"] == "declared_explicit"
    assert payload["provenance"]["sources"]["portfolio"]["as_of"] == "2026-08-20"
    assert payload["provenance"]["archive"]["archive_version"] == 1


def test_ingest_endpoint_rejects_invalid_declared_date():
    with open(FIXDIR / "portfolio.csv", "rb") as pf, \
         open(FIXDIR / "screener.csv", "rb") as sf, \
         open(FIXDIR / "ledger.csv", "rb") as lf:
        resp = client.post("/api/v1/ingest", files=[
            ("portfolio", ("portfolio.csv", pf.read(), "text/csv")),
            ("screener", ("screener.csv", sf.read(), "text/csv")),
            ("ledger", ("ledger.csv", lf.read(), "text/csv")),
        ], data={"ledger_as_of": "August 2026"})
    assert resp.status_code == 400
    body = resp.json()["detail"]["error"]
    assert body["code"] == "IMPORT_ERROR"
    assert "YYYY-MM-DD" in body["message"]


# --- D10.2 capture-before-parse guarantee & what-if non-persistence ---------------


def test_raw_bytes_captured_even_when_parse_fails():
    bad = b"not,a,csv\r\n\x00,broken\xff,bytes\r\n"
    entries_before = len(archive.read_manifest())
    with open(FIXDIR / "screener.csv", "rb") as sf, \
         open(FIXDIR / "ledger.csv", "rb") as lf:
        resp = client.post("/api/v1/run", files=[
            ("portfolio", ("portfolio.csv", bad, "text/csv")),
            ("screener", ("screener.csv", sf.read(), "text/csv")),
            ("ledger", ("ledger.csv", lf.read(), "text/csv")),
        ])
    assert resp.status_code == 400, resp.text
    sha = hashlib.sha256(bad).hexdigest()
    assert archive.blob_path_for(sha).read_bytes() == bad, \
        "raw evidence of the corrupt upload must exist even though the run never started"
    assert len(archive.read_manifest()) == entries_before, \
        "no manifest entry is written for an ingestion event that never ran"


def test_what_if_never_archives():
    _fixture_run()
    count = len(archive.read_manifest())
    resp = client.post("/api/v1/what-if", json={"run_id": None, "policy_overrides": None})
    assert resp.status_code == 200, resp.text
    assert len(archive.read_manifest()) == count, \
        "/what-if must not persist into the run store or the snapshot archive"
