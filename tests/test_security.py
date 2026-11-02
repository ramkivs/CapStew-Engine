"""Security regression tests for the locally hosted personal application.

These pin the fixes for the defects found in the repository audit:
  * arbitrary file write via a traversal upload filename (CRITICAL)
  * unauthenticated tampering with the signed policy file (CRITICAL)
  * weight-sum and unknown-key validation gaps
  * run-store immutability
Every test asserts the *rejection* path, not just the happy path.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.config as cfg
from app.main import app
from app.store import RunStore, RunStoreError

client = TestClient(app)
FIXDIR = Path(__file__).resolve().parent.parent / "fixtures"
SIGNED_POLICY = Path(__file__).resolve().parent.parent / "policy" / "policy.yaml"


def _bytes(name):
    return (FIXDIR / name).read_bytes()


def _files(ledger_name="ledger.csv"):
    return {
        "portfolio": ("portfolio.csv", _bytes("portfolio.csv"), "text/csv"),
        "screener": ("screener.csv", _bytes("screener.csv"), "text/csv"),
        "ledger": (ledger_name, _bytes("ledger.csv"), "text/csv"),
    }


# ---- 1. upload filename confinement -----------------------------------------

@pytest.mark.parametrize("endpoint", ["/api/v1/ingest", "/api/v1/run"])
def test_traversal_filename_is_rejected(endpoint, tmp_path):
    """A `../` filename must not escape the upload directory (audit R-01)."""
    target = tmp_path / "ESCAPED.csv"
    files = _files(ledger_name="../../../../../../" + str(target) + ".csv")
    r = client.post(endpoint, files=files)
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "FILE_PARSE_ERROR"
    assert not target.exists(), "file was written outside the upload directory"


@pytest.mark.parametrize("endpoint", ["/api/v1/ingest", "/api/v1/run"])
def test_absolute_path_filename_is_rejected(endpoint, tmp_path):
    target = tmp_path / "ABSOLUTE.csv"
    files = _files(ledger_name=str(target))
    r = client.post(endpoint, files=files)
    assert r.status_code == 400
    assert not target.exists()


@pytest.mark.parametrize("endpoint", ["/api/v1/ingest", "/api/v1/run"])
def test_backslash_traversal_is_rejected(endpoint):
    """Windows-style separators must be stripped too — this is a Windows app."""
    files = _files(ledger_name="..\\..\\..\\..\\WINDOWS_ESCAPE.csv")
    r = client.post(endpoint, files=files)
    assert r.status_code == 400


@pytest.mark.parametrize("endpoint", ["/api/v1/ingest", "/api/v1/run"])
def test_non_csv_still_rejected(endpoint):
    files = _files(ledger_name="ledger.txt")
    r = client.post(endpoint, files=files)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "FILE_PARSE_ERROR"


def test_traversal_suffix_spoof_is_rejected():
    """`evil.csv/../../x.csv` — the suffix check must run on the sanitized name."""
    files = _files(ledger_name="../../../../tmp/x.csv/../../y.csv")
    assert client.post("/api/v1/ingest", files=files).status_code == 400


def test_plain_basename_upload_still_works():
    """The fix must not break ordinary uploads."""
    r = client.post("/api/v1/ingest", files=_files())
    assert r.status_code == 200, r.text
    assert len(r.json()["positions"]) == 9


# ---- 2. signed policy protection --------------------------------------------

def test_put_policy_never_writes_the_signed_file(tmp_path, monkeypatch):
    """The shipped, git-tracked policy.yaml must be immutable at runtime (R-02)."""
    monkeypatch.setattr(cfg, "USER_POLICY_PATH", tmp_path / "user-policy.yaml")
    before = SIGNED_POLICY.read_bytes()
    r = client.put("/api/v1/policy", json={"pledge_threshold_pct": 999.0})
    assert r.status_code == 200, r.text
    assert SIGNED_POLICY.read_bytes() == before
    # the override landed in the app-managed data directory instead
    assert (tmp_path / "user-policy.yaml").exists()


def test_put_policy_rejects_arbitrary_key_injection(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "USER_POLICY_PATH", tmp_path / "user-policy.yaml")
    r = client.put("/api/v1/policy", json={"EVIL_KEY": "injected"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "POLICY_INVALID"
    assert not (tmp_path / "user-policy.yaml").exists()


def test_put_policy_rejects_weight_set_not_summing_to_100(tmp_path, monkeypatch):
    """D-09 — sum 600 used to be accepted and silently rescaled every score."""
    monkeypatch.setattr(cfg, "USER_POLICY_PATH", tmp_path / "user-policy.yaml")
    r = client.put("/api/v1/policy", json={"weights": {
        "position_sizing": 100, "valuation_stretch": 100, "quality_drift": 100,
        "tax_efficiency": 100, "opportunity_cost": 100, "technical_regime": 100}})
    assert r.status_code == 422
    assert "must sum to 100" in str(r.json()["error"])


def test_user_override_is_isolated_per_data_dir(tmp_path, monkeypatch):
    """Committing policy in one data dir must not leak into another."""
    monkeypatch.setattr(cfg, "USER_POLICY_PATH", tmp_path / "user-policy.yaml")
    good = {**client.get("/api/v1/policy").json()["weights"], "technical_regime": 10}
    good["position_sizing"] = 100 - sum(v for k, v in good.items() if k != "position_sizing")
    assert client.put("/api/v1/policy", json={"weights": good}).status_code == 200
    assert client.get("/api/v1/policy").json()["weights"]["technical_regime"] == 10

    other = tmp_path / "other" / "policy.yaml"
    monkeypatch.setattr(cfg, "USER_POLICY_PATH", other)
    assert client.get("/api/v1/policy").json()["weights"]["technical_regime"] == 5


# ---- 3. run-store immutability ----------------------------------------------

def test_duplicate_run_id_is_rejected(tmp_path):
    """ADR-4: the store is append-only; INSERT OR REPLACE silently overwrote."""
    cfg.STORE_PATH = tmp_path / "engine.db"
    store = RunStore()
    payload = {"run_id": "r1", "as_of": "2026-08-22", "engine_version": "x",
               "policy_version": 1, "content_hash": "AAA", "holdings": [],
               "portfolio_summary": {}}
    store.save_run(payload)
    tampered = dict(payload, content_hash="BBB-TAMPERED")
    with pytest.raises(RunStoreError):
        store.save_run(tampered)
    assert store.count() == 1
    assert store.get_run("r1")["content_hash"] == "AAA", "original record was overwritten"
    store.close()


# ---- 4. uniform error envelope ----------------------------------------------

def test_all_errors_use_one_envelope():
    for url in ("/api/v1/decisions?run_id=NOPE",
                "/api/v1/holdings/NOPE",
                "/api/v1/runs/NOPE/diff"):
        r = client.get(url)
        assert r.status_code == 404
        body = r.json()
        assert "detail" not in body, f"{url} still uses the FastAPI default shape"
        assert body["error"]["code"] == "NOT_FOUND"
        assert body["error"]["message"]


def test_validation_error_uses_envelope():
    r = client.get("/api/v1/tax-tracker?fy=not-a-fy")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
