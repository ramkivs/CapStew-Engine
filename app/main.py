"""Capital Steward Engine — FastAPI service.

Phase 1 (data foundation): /health, /reconcile, /ingest, /lots/{instrument}
Phase 2 (decision engine):  /run, /what-if, /decisions, /holdings/{id}, /runs, /policy

Runs are persisted to the append-only store (ADR-4). Hysteresis state on /run is
derived from the previously PERSISTED run — never process memory — so decisions
survive restart (audit item B). /what-if never persists and never mutates policy.
"""
import tempfile
from datetime import date
from pathlib import Path

import yaml
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from . import archive, config
from .ingest import IngestError, parse_ledger, parse_portfolio, parse_screener, parse_sold
from .pipeline import decide_on_foundation, resolve_slot_as_of, run_foundation
from .schema import DecisionPayloadValidationError, validate_decision_payload
from .store import RunStore

app = FastAPI(
    title="Capital Steward Engine",
    description="Portfolio discipline · valuation · tax · risk",
    version=config.ENGINE_VERSION,
)

# In-memory cache of the most recent foundation (single-process local v1).
_LAST_FOUNDATION: dict = {}
_LAST_TAX: dict = {}


def _payload_validation_failure(exc: DecisionPayloadValidationError):
    raise HTTPException(
        status_code=500,
        detail={
            "error": {
                "code": "INTERNAL_ERROR",
                "severity": "blocking",
                "message": "internal DecisionPayload validation failed",
                "details": {"errors": list(exc.errors)},
            }
        },
    ) from exc


def _save(upload: UploadFile, dirpath: Path) -> Path:
    if not upload.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail=f"{upload.filename}: only .csv accepted")
    dest = dirpath / upload.filename
    dest.write_bytes(upload.file.read())
    return dest


def _save_and_capture(slot: str, upload: UploadFile, dirpath: Path) -> Path:
    """CR-022 ingestion hook: archive the exact received bytes BEFORE any parse.

    The blob capture is content-addressed and idempotent; the parse-dependent
    manifest record is finalized later by the pipeline/manifest appenders.
    """
    dest = _save(upload, dirpath)
    archive.capture_file(slot, dest)
    return dest


def _parse_declared(slot: str, value: str | None) -> str | None:
    """Explicit declared source-date (F2-D3). Invalid dates are rejected, never
    silently coerced."""
    if value in (None, ""):
        return None
    try:
        date.fromisoformat(value.strip())
    except ValueError:
        _api_error(400, "IMPORT_ERROR",
                   f"{value!r}: declared {slot} as_of must be YYYY-MM-DD",
                   stage=f"declared_as_of:{slot}")
    return value.strip()


def _api_error(status: int, code: str, message: str, *, stage: str | None = None,
               file: str | None = None):
    """Structured error envelope (additive diagnostics channel).

    FastAPI serializes `detail` verbatim, so clients receive
    {"detail": {"error": {code, severity, stage?, file?, message}}}.
    """
    err = {"code": code, "severity": "blocking", "message": message}
    if stage:
        err["stage"] = stage
    if file:
        err["file"] = file
    raise HTTPException(status_code=status, detail={"error": err})


def _precheck(slot: str, upload: UploadFile, path: Path, parse_fn) -> None:
    """Attribute ingest failures to the right uploaded file/slot.

    Runs only the tolerant CSV parser for that slot — no engine execution, no
    methodology involvement. The engine re-parses everything itself downstream;
    this duplicate pass exists purely so the user sees 'portfolio.csv line 42 …'
    instead of an opaque 500.
    """
    try:
        parse_fn(path)
    except IngestError as exc:
        _api_error(400, "IMPORT_ERROR", str(exc), stage=f"parse:{slot}", file=upload.filename)
    except Exception as exc:
        _api_error(400, "IMPORT_ERROR", f"{type(exc).__name__}: {exc}",
                   stage=f"parse:{slot}", file=upload.filename)


def _engine_error(stage: str, exc: Exception):
    """Map engine-side exceptions to structured responses without hiding them."""
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, IngestError):
        _api_error(400, "IMPORT_ERROR", str(exc), stage=stage)
    if isinstance(exc, (ValueError, TypeError, AttributeError, KeyError)):
        _api_error(400, "IMPORT_ERROR", f"{type(exc).__name__}: {exc}", stage=stage)
    _api_error(500, "ENGINE_ERROR", f"{type(exc).__name__}: {exc}", stage=stage)


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
        _precheck("portfolio", portfolio, p, parse_portfolio)
        _precheck("ledger", ledger, l, parse_ledger)
        tol = Decimal(str(get_recon_tolerance(load_policy())))
        try:
            return reconcile(parse_portfolio(p), parse_ledger(l), tol)
        except Exception as exc:
            _engine_error("reconcile", exc)


@app.post("/api/v1/ingest")
def ingest_endpoint(
    portfolio: UploadFile = File(...),
    screener: UploadFile = File(...),
    ledger: UploadFile = File(...),
    # CR-022 / F2-D3: optional explicit declared source dates (YYYY-MM-DD).
    portfolio_as_of: str | None = Form(default=None),
    screener_as_of: str | None = Form(default=None),
    ledger_as_of: str | None = Form(default=None),
):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        p = _save_and_capture("portfolio", portfolio, tmp)
        s = _save_and_capture("screener", screener, tmp)
        l = _save_and_capture("ledger", ledger, tmp)
        declared = {slot: _parse_declared(slot, v) for slot, v in
                    (("portfolio", portfolio_as_of), ("screener", screener_as_of),
                     ("ledger", ledger_as_of))}
        _precheck("portfolio", portfolio, p, parse_portfolio)
        _precheck("screener", screener, s, parse_screener)
        _precheck("ledger", ledger, l, parse_ledger)
        try:
            payload = run_foundation(p, s, l, declared_as_of=declared)
        except Exception as exc:
            _engine_error("ingest", exc)
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
    # CR-022 / F2-D3: optional explicit declared source dates (YYYY-MM-DD).
    portfolio_as_of: str | None = Form(default=None),
    screener_as_of: str | None = Form(default=None),
    ledger_as_of: str | None = Form(default=None),
    sold_as_of: str | None = Form(default=None),
):
    from .pipeline import compute_tax_year
    store = None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            p = _save_and_capture("portfolio", portfolio, tmp)
            s = _save_and_capture("screener", screener, tmp)
            l = _save_and_capture("ledger", ledger, tmp)
            declared = {slot: _parse_declared(slot, v) for slot, v in
                        (("portfolio", portfolio_as_of), ("screener", screener_as_of),
                         ("ledger", ledger_as_of))}
            _precheck("portfolio", portfolio, p, parse_portfolio)
            _precheck("screener", screener, s, parse_screener)
            _precheck("ledger", ledger, l, parse_ledger)
            foundation = run_foundation(p, s, l, declared_as_of=declared)
            store = RunStore()
            history = store.previous_holdings()          # persisted prior run, not memory
            payload = decide_on_foundation(foundation, apply_hysteresis=True, history=history)
            if sold is not None:
                sp = _save_and_capture("sold", sold, tmp)
                _precheck("sold", sold, sp, parse_sold)
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
                # CR-022: sold slot joins the run's archive lineage (F2-D2).
                sold_dates = resolve_slot_as_of(
                    "sold", sp, {"sold": _parse_declared("sold", sold_as_of)})
                sold_record = archive.capture_file(
                    "sold", sp,
                    declared_source_as_of=sold_dates["declared_source_as_of"],
                    as_of_source=sold_dates["as_of_source"])
                sold_record["rows"] = len(parse_sold(sp))
                sold_record["parse_status"] = "ok"
                archive.append_slot(run_id=payload["run_id"],
                                    file_record=sold_record,
                                    policy_version=payload["policy_version"])
                _LAST_TAX.clear(); _LAST_TAX.update(tax)
            validate_decision_payload(payload)
            store.save_run(payload, validate=True)
            # CR-022 / F2-D2: link the persisted decision run to its evidence.
            archive.append_run_link(run_id=payload["run_id"],
                                    input_hash=payload["input_hash"],
                                    decision_content_hash=payload["content_hash"],
                                    policy_version=payload["policy_version"])
            _LAST_FOUNDATION.clear(); _LAST_FOUNDATION.update(foundation)
            return payload
    except DecisionPayloadValidationError as exc:
        _payload_validation_failure(exc)
    except Exception as exc:
        _engine_error("run", exc)
    finally:
        if store is not None:
            store.close()


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

    store = None
    try:
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
        validate_decision_payload(payload)
        store.save_run(payload, validate=True)
        # CR-022 / F2-D2: link the persisted decision run to its evidence.
        archive.append_run_link(run_id=payload["run_id"],
                                input_hash=payload["input_hash"],
                                decision_content_hash=payload["content_hash"],
                                policy_version=payload["policy_version"])
        _LAST_FOUNDATION.clear(); _LAST_FOUNDATION.update(foundation)
        return payload
    except DecisionPayloadValidationError as exc:
        _payload_validation_failure(exc)
    finally:
        if store is not None:
            store.close()


@app.post("/api/v1/what-if")
def what_if(req: WhatIfRequest):
    if not _LAST_FOUNDATION:
        raise HTTPException(status_code=404, detail="no run yet — POST /api/v1/run first")
    try:
        # Fresh hysteresis, no history, no persistence, no policy mutation.
        payload = decide_on_foundation(_LAST_FOUNDATION, policy_overrides=req.policy_overrides,
                                       apply_hysteresis=False)
        payload["run_id"] = "whatif_" + (req.run_id or _LAST_FOUNDATION["run_id"])
        return validate_decision_payload(payload)
    except DecisionPayloadValidationError as exc:
        _payload_validation_failure(exc)


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


@app.get("/api/v1/themes")
def get_themes():
    """Read-only readout of the authority theme mapping document (CR-023).

    Display support only (H2-D10/UI constraint): there is deliberately NO
    POST/PUT — the document is authority-controlled and not user-editable.
    An invalid document is a blocking configuration failure, never repaired.
    """
    import hashlib as _hashlib

    from . import themes as themes_mod
    try:
        doc = themes_mod.load_and_validate()
    except Exception as exc:
        _api_error(500, "ENGINE_ERROR", f"theme mapping document invalid: {exc}",
                   stage="themes")
    data = themes_mod.document_bytes()
    return {
        **doc,
        "sha256": _hashlib.sha256(data).hexdigest() if data is not None else None,
        "document": "themes/themes.yaml",
        "control": "authority-controlled (H2-D5-A) — read-only via API",
    }


# ---- CR-024 (EMM-F2) — read-only historical evidence surfaces ------------------
# Date-indexed historical fundamentals store/query + G-04 median + G1 history
# legs. Strictly read-only: there is deliberately NO POST/PUT/DELETE — the
# archive is append-only and historical evidence is not user-editable.
# G-04 is NOT ACTIVATED (peer proxy in force); G1 gate semantics unchanged.


def _hist_as_of(as_of: str | None) -> str:
    from . import history as hist_mod
    resolved = as_of or hist_mod.latest_archived_as_of()
    if resolved is None:
        _api_error(404, "NOT_FOUND", "no archived ingest events yet", stage="history")
    return resolved


@app.get("/api/v1/history/fundamentals/{instrument}")
def get_history_fundamentals(instrument: str, metric: str | None = None,
                             start: str | None = None, end: str | None = None,
                             as_of: str | None = None):
    """Date-indexed historical fundamentals query — NO run_id required (F2-D1-A)."""
    from . import history as hist_mod
    try:
        result = hist_mod.query_fundamentals(instrument, metric=metric, start=start,
                                             end=end, as_of=as_of)
    except Exception as exc:
        _engine_error("history", exc)
    if result["observation_count"] == 0:
        raise HTTPException(
            status_code=404,
            detail=f"no archived observations for instrument {instrument!r}"
                   + (f" metric {metric!r}" if metric else ""))
    return result


@app.get("/api/v1/history/g04/{instrument}")
def get_history_g04(instrument: str, as_of: str | None = None):
    """G-04 own-history PE/PB median evidence (G04-MEDIAN-METHODOLOGY-v1).

    IMPLEMENTED BUT NOT ACTIVATED: production scoring remains on the
    peer-relative proxy (G04-D9-A / F2-I5-A).
    """
    from . import history as hist_mod
    try:
        return hist_mod.pe_pb_medians(instrument, _hist_as_of(as_of))
    except Exception as exc:
        _engine_error("history", exc)


@app.get("/api/v1/history/g1/{instrument}")
def get_history_g1(instrument: str, as_of: str | None = None):
    """G1 history legs evidence (G1-HISTORY-LEGS-METHODOLOGY-v1).

    EVIDENCE ONLY: existing G1 gate behavior is unchanged (F2-I6-A / G1-D11-A).
    """
    from . import history as hist_mod
    try:
        return hist_mod.g1_legs(instrument, _hist_as_of(as_of))
    except Exception as exc:
        _engine_error("history", exc)


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
