"""Capital Steward Engine — FastAPI service.

Phase 1 (data foundation): /health, /reconcile, /ingest, /lots/{instrument}
Phase 2 (decision engine):  /run, /what-if, /decisions, /holdings/{id}, /runs, /policy

Runs are persisted to the append-only store (ADR-4). Hysteresis state on /run is
derived from the previously PERSISTED run — never process memory — so decisions
survive restart (audit item B). /what-if never persists and never mutates policy.
"""
import tempfile
from pathlib import Path

import yaml
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from . import config
from .pipeline import decide_on_foundation, run_foundation
from .store import RunStore

app = FastAPI(
    title="Capital Steward Engine",
    description="Portfolio discipline · valuation · tax · risk",
    version=config.ENGINE_VERSION,
)

# In-memory cache of the most recent foundation (single-process local v1).
_LAST_FOUNDATION: dict = {}
_LAST_TAX: dict = {}


def _save(upload: UploadFile, dirpath: Path) -> Path:
    if not upload.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail=f"{upload.filename}: only .csv accepted")
    dest = dirpath / upload.filename
    dest.write_bytes(upload.file.read())
    return dest


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "engine_version": config.ENGINE_VERSION, "phase": config.PHASE}


@app.post("/api/v1/reconcile")
def reconcile_endpoint(
    portfolio: UploadFile = File(...),
    ledger: UploadFile = File(...),
):
    from decimal import Decimal

    from .ingest import parse_ledger, parse_portfolio
    from .policy import get_recon_tolerance, load_policy
    from .reconcile import reconcile

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        p = _save(portfolio, tmp)
        l = _save(ledger, tmp)
        tol = Decimal(str(get_recon_tolerance(load_policy())))
        return reconcile(parse_portfolio(p), parse_ledger(l), tol)


@app.post("/api/v1/ingest")
def ingest_endpoint(
    portfolio: UploadFile = File(...),
    screener: UploadFile = File(...),
    ledger: UploadFile = File(...),
):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        p = _save(portfolio, tmp)
        s = _save(screener, tmp)
        l = _save(ledger, tmp)
        payload = run_foundation(p, s, l)
        _LAST_FOUNDATION.clear()
        _LAST_FOUNDATION.update(payload)
        return payload


@app.get("/api/v1/lots/{instrument}")
def lots_for(instrument: str):
    if not _LAST_FOUNDATION:
        raise HTTPException(status_code=404, detail="no ingest run yet")
    lots = [l for l in _LAST_FOUNDATION.get("lots", []) if l["instrument"] == instrument]
    if not lots:
        raise HTTPException(status_code=404, detail=f"no lots for {instrument!r} in last run")
    return lots


# ---------------- Phase 2 — decision engine ----------------

@app.post("/api/v1/run")
def run_endpoint(
    portfolio: UploadFile = File(...),
    screener: UploadFile = File(...),
    ledger: UploadFile = File(...),
    sold: UploadFile | None = File(default=None),
):
    from .pipeline import compute_tax_year
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        p = _save(portfolio, tmp)
        s = _save(screener, tmp)
        l = _save(ledger, tmp)
        foundation = run_foundation(p, s, l)
        store = RunStore()
        history = store.previous_holdings()          # persisted prior run, not memory
        payload = decide_on_foundation(foundation, apply_hysteresis=True, history=history)
        if sold is not None:
            sp = _save(sold, tmp)
            tax = compute_tax_year(foundation, sp)
            payload["tax_year"] = tax
            payload["portfolio_summary"]["tax"].update({
                "provisional": False,
                "ltcg_booked": tax["summary"]["gross"]["ltcg"],
                "stcg_booked": tax["summary"]["gross"]["stcg"],
                "ltcg_headroom": tax["summary"]["exemption"]["headroom"],
                "stcl_harvestable": tax["summary"]["gross"]["stcl"],
                "note": "realised from sold.csv (FIFO-matched) + unrealised split of open book",
            })
            _LAST_TAX.clear(); _LAST_TAX.update(tax)
        store.save_run(payload)
        store.close()
        _LAST_FOUNDATION.clear(); _LAST_FOUNDATION.update(foundation)
        return payload


class WhatIfRequest(BaseModel):
    run_id: str | None = None
    policy_overrides: dict | None = None


@app.post("/api/v1/run-sample")
def run_sample_endpoint():
    """Run the bundled fixtures through the full engine (foundation → decisions → tax).

    Lets the UI demo and the acceptance test exercise the authoritative pipeline
    without file uploads. Persists the run like /run does.
    """
    from pathlib import Path as P

    from .pipeline import compute_tax_year

    fx = P(__file__).resolve().parent.parent / "fixtures"
    foundation = run_foundation(fx / "portfolio.csv", fx / "screener.csv", fx / "ledger.csv")
    store = RunStore()
    history = store.previous_holdings()
    payload = decide_on_foundation(foundation, apply_hysteresis=True, history=history)
    sold = fx / "sold_sample.csv"
    if sold.exists():
        tax = compute_tax_year(foundation, sold)
        payload["tax_year"] = tax
        payload["portfolio_summary"]["tax"].update({
            "provisional": False,
            "ltcg_booked": tax["summary"]["gross"]["ltcg"],
            "stcg_booked": tax["summary"]["gross"]["stcg"],
            "ltcg_headroom": tax["summary"]["exemption"]["headroom"],
            "stcl_harvestable": tax["summary"]["gross"]["stcl"],
            "note": "realised from fixtures/sold_sample.csv (FIFO-matched) + unrealised split of open book",
        })
        _LAST_TAX.clear(); _LAST_TAX.update(tax)
    store.save_run(payload)
    store.close()
    _LAST_FOUNDATION.clear(); _LAST_FOUNDATION.update(foundation)
    return payload


@app.post("/api/v1/what-if")
def what_if(req: WhatIfRequest):
    if not _LAST_FOUNDATION:
        raise HTTPException(status_code=404, detail="no run yet — POST /api/v1/run first")
    # Fresh hysteresis, no history, no persistence, no policy mutation.
    payload = decide_on_foundation(_LAST_FOUNDATION, policy_overrides=req.policy_overrides,
                                   apply_hysteresis=False)
    payload["run_id"] = "whatif_" + (req.run_id or _LAST_FOUNDATION["run_id"])
    return payload


@app.get("/api/v1/decisions")
def decisions(run_id: str | None = None):
    store = RunStore()
    try:
        if run_id:
            payload = store.get_run(run_id)
            if payload is None:
                raise HTTPException(status_code=404, detail=f"run {run_id} not found")
            return payload
        payload = store.latest_run()
        if payload is None:
            raise HTTPException(status_code=404, detail="no run yet")
        return payload
    finally:
        store.close()


@app.get("/api/v1/holdings/{instrument}")
def holding(instrument: str):
    store = RunStore()
    try:
        payload = store.latest_run()
        if payload is None:
            raise HTTPException(status_code=404, detail="no run yet")
        for h in payload["holdings"]:
            if h["instrument"] == instrument:
                return h
    finally:
        store.close()
    raise HTTPException(status_code=404, detail=f"no holding {instrument!r} in last run")


@app.get("/api/v1/runs")
def runs():
    store = RunStore()
    try:
        return store.list_runs()
    finally:
        store.close()


@app.get("/api/v1/runs/{run_id}/diff")
def run_diff(run_id: str):
    store = RunStore()
    try:
        d = store.diff(run_id)
        if d is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")
        return d
    finally:
        store.close()


@app.get("/api/v1/tax-tracker")
def tax_tracker(fy: str = "2026-27"):
    if not _LAST_TAX:
        raise HTTPException(
            status_code=404,
            detail="no realised-gains data — POST /api/v1/run with a sold.csv to compute the tax year",
        )
    return _LAST_TAX


@app.get("/api/v1/policy")
def get_policy():
    from .policy import load_policy
    return load_policy()


@app.put("/api/v1/policy")
def put_policy(body: dict):
    from .policy import POLICY_PATH, load_policy, validate_policy
    current = load_policy()
    merged = {**current, **body}
    if body.get("weights"):
        merged["weights"] = {**current.get("weights", {}), **body["weights"]}
    errors = validate_policy(merged)
    if errors:
        raise HTTPException(status_code=422, detail={"POLICY_INVALID": errors})
    merged["policy_version"] = int(current.get("policy_version", 0)) + 1
    POLICY_PATH.write_text(yaml.safe_dump(merged, sort_keys=False, allow_unicode=True))
    return merged
