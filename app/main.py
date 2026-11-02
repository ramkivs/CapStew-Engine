"""Capital Steward Engine — FastAPI service.

Phase 1 (data foundation): /health, /reconcile, /ingest, /lots/{instrument}
Phase 2 (decision engine):  /run, /what-if, /decisions, /holdings/{id}, /runs, /policy

Runs are persisted to the append-only store (ADR-4). Hysteresis state on /run is
derived from the previously PERSISTED run — never process memory — so decisions
and N=2 confirmation counters survive restart (audit item B / Freeze §6).
/what-if never persists and never mutates policy.

Deployment model: PERSONAL, SINGLE-USER, LOCALLY HOSTED (ADR-3). Bind the server
to 127.0.0.1 (see scripts/start.bat / scripts/start.sh) so it is reachable only
from this machine. Errors use one uniform envelope (architecture §11.6).
"""
import re
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import config
from .pipeline import DataAsOfError, decide_on_foundation, run_foundation
from .schema import DecisionPayloadValidationError, validate_decision_payload
from .store import RunStore, RunStoreError

app = FastAPI(
    title="Capital Steward Engine",
    description="Portfolio discipline · valuation · tax · risk — personal local use",
    version=config.ENGINE_VERSION,
)

# In-memory cache of the most recent foundation (single-process local v1).
_LAST_FOUNDATION: dict = {}
_LAST_TAX: dict = {}

_FY_RE = re.compile(r"^\d{4}-\d{2}$")
CSV_SUFFIX = ".csv"
DEFAULT_FY = "2026-27"


# ---------------- uniform error envelope (architecture §11.6) ----------------

_STATUS_CODE = {400: "BAD_REQUEST", 404: "NOT_FOUND", 409: "CONFLICT",
                422: "VALIDATION_ERROR", 500: "INTERNAL_ERROR"}


def _error(code, message, severity="warning", status=400, details=None):
    body = {"code": code, "severity": severity, "message": message}
    if details:
        body["details"] = details
    raise HTTPException(status_code=status, detail={"error": body})


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and isinstance(detail.get("error"), dict):
        body = detail                                  # already enveloped
    else:
        body = {"error": {
            "code": _STATUS_CODE.get(exc.status_code, "ERROR"),
            "severity": "blocking" if exc.status_code >= 500 else "warning",
            "message": str(detail),
        }}
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": {
        "code": "VALIDATION_ERROR", "severity": "warning",
        "message": "request validation failed",
        "details": {"errors": exc.errors()},
    }})


@app.exception_handler(DataAsOfError)
async def _data_as_of_handler(request: Request, exc: DataAsOfError):
    return JSONResponse(status_code=400, content={"error": {
        "code": "DATE_AMBIGUOUS", "severity": "warning", "message": str(exc)}})


@app.exception_handler(RunStoreError)
async def _run_store_handler(request: Request, exc: RunStoreError):
    return JSONResponse(status_code=409, content={"error": {
        "code": "CONFLICT", "severity": "blocking", "message": str(exc)}})


def _payload_validation_failure(exc: DecisionPayloadValidationError):
    _error("INTERNAL_ERROR", "internal DecisionPayload validation failed",
           severity="blocking", status=500, details={"errors": list(exc.errors)})


# ---------------- upload handling ----------------

def _safe_dest(upload: UploadFile, dirpath: Path) -> Path:
    """Confine an upload to `dirpath`.

    The client controls `filename`, so it is validated before use. Without this a
    filename such as `../../x.csv` wrote outside the sandbox (arbitrary file
    write, audit R-01). A legitimate CSV upload never carries a path, so a
    filename containing a separator or a traversal component is REJECTED rather
    than silently renamed — renaming would hide malformed or hostile input.
    The resolved path is re-checked as defence in depth.
    """
    raw = upload.filename or ""
    if not raw:
        _error("FILE_PARSE_ERROR", "upload has no filename", status=400)
    normalized = raw.replace("\\", "/")
    if ".." in normalized.split("/") or "/" in normalized.strip("/"):
        _error("FILE_PARSE_ERROR",
               f"{raw!r}: filename must not contain a path — upload the file itself",
               status=400)
    name = Path(normalized).name                       # strip any directory part
    if not name.lower().endswith(CSV_SUFFIX):
        _error("FILE_PARSE_ERROR", f"{raw}: only .csv accepted", status=400)
    if name.startswith(".") or name in ("", ".", ".."):
        _error("FILE_PARSE_ERROR", f"{raw!r}: not a usable filename", status=400)
    dest = (dirpath / name).resolve()
    if not dest.is_relative_to(dirpath.resolve()):
        _error("FILE_PARSE_ERROR", f"{raw!r}: filename escapes the upload directory",
               status=400)
    return dest


def _save(upload: UploadFile, dirpath: Path) -> Path:
    dest = _safe_dest(upload, dirpath)
    dest.write_bytes(upload.file.read())
    return dest


def _parse_as_of(value):
    """Optional `as_of` form field → date, or None when absent."""
    from datetime import date as _date
    if value in (None, ""):
        return None
    try:
        return _date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise DataAsOfError(f"as_of must be an ISO date (YYYY-MM-DD), got {value!r}") from exc


def _parse_data_as_of(portfolio, screener, ledger):
    """Optional per-source data dates → dict, or None when none supplied."""
    declared = {k: v for k, v in (("portfolio", portfolio), ("screener", screener),
                                  ("ledger", ledger)) if v not in (None, "")}
    return declared or None


# ---------------- Phase 1 ----------------

@app.get("/api/v1/health")
def health():
    """Liveness + engine version + data-as-of of the last run (§11.6)."""
    body = {"status": "ok", "engine_version": config.ENGINE_VERSION, "phase": config.PHASE}
    if _LAST_FOUNDATION:
        body["data_as_of"] = _LAST_FOUNDATION.get("data_as_of")
        body["last_run_id"] = _LAST_FOUNDATION.get("run_id")
    return body


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
    as_of: str | None = Form(default=None),
    data_as_of_portfolio: str | None = Form(default=None),
    data_as_of_screener: str | None = Form(default=None),
    data_as_of_ledger: str | None = Form(default=None),
):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        p = _save(portfolio, tmp)
        s = _save(screener, tmp)
        l = _save(ledger, tmp)
        payload = run_foundation(
            p, s, l, as_of=_parse_as_of(as_of),
            data_as_of=_parse_data_as_of(data_as_of_portfolio, data_as_of_screener,
                                         data_as_of_ledger))
        _LAST_FOUNDATION.clear()
        _LAST_FOUNDATION.update(payload)
        return payload


@app.get("/api/v1/lots/{instrument}")
def lots_for(instrument: str):
    if not _LAST_FOUNDATION:
        _error("NOT_FOUND", "no ingest run yet", status=404)
    lots = [l for l in _LAST_FOUNDATION.get("lots", [])
            if l["instrument"] == instrument or l.get("ticker") == instrument]
    if not lots:
        _error("NO_LOTS", f"no lots for {instrument!r} in last run", status=404)
    return lots


# ---------------- Phase 2 — decision engine ----------------

def _attach_tax(payload, foundation, sold_path, source_label, fy=DEFAULT_FY):
    from .pipeline import compute_tax_year

    tax = compute_tax_year(foundation, sold_path, fy=fy)
    payload["tax_year"] = tax
    payload["portfolio_summary"]["tax"].update({
        "provisional": False,
        "ltcg_booked": tax["summary"]["gross"]["ltcg"],
        "stcg_booked": tax["summary"]["gross"]["stcg"],
        "ltcg_headroom": tax["summary"]["exemption"]["headroom"],
        "stcl_harvestable": tax["summary"]["gross"]["stcl"],
        "note": f"realised from {source_label} (FIFO-matched) + unrealised split of open book",
    })
    _LAST_TAX.clear()
    _LAST_TAX.update(tax)
    _LAST_TAX["fy"] = tax["summary"].get("fy", fy)


@app.post("/api/v1/run")
def run_endpoint(
    portfolio: UploadFile = File(...),
    screener: UploadFile = File(...),
    ledger: UploadFile = File(...),
    sold: UploadFile | None = File(default=None),
    as_of: str | None = Form(default=None),
    data_as_of_portfolio: str | None = Form(default=None),
    data_as_of_screener: str | None = Form(default=None),
    data_as_of_ledger: str | None = Form(default=None),
):
    store = None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            p = _save(portfolio, tmp)
            s = _save(screener, tmp)
            l = _save(ledger, tmp)
            foundation = run_foundation(
                p, s, l, as_of=_parse_as_of(as_of),
                data_as_of=_parse_data_as_of(data_as_of_portfolio, data_as_of_screener,
                                             data_as_of_ledger))
            store = RunStore()
            history = store.previous_holdings()          # persisted prior run, not memory
            payload = decide_on_foundation(foundation, apply_hysteresis=True, history=history)
            if sold is not None:
                sp = _save(sold, tmp)
                _attach_tax(payload, foundation, sp, "sold.csv")
            validate_decision_payload(payload)
            store.save_run(payload, validate=True)
            _LAST_FOUNDATION.clear()
            _LAST_FOUNDATION.update(foundation)
            return payload
    except DecisionPayloadValidationError as exc:
        _payload_validation_failure(exc)
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
    store = None
    try:
        fx = config.ROOT / "fixtures"
        foundation = run_foundation(fx / "portfolio.csv", fx / "screener.csv",
                                    fx / "ledger.csv")
        store = RunStore()
        history = store.previous_holdings()
        payload = decide_on_foundation(foundation, apply_hysteresis=True, history=history)
        sold = fx / "sold_sample.csv"
        if sold.exists():
            _attach_tax(payload, foundation, sold, "fixtures/sold_sample.csv")
        validate_decision_payload(payload)
        store.save_run(payload, validate=True)
        _LAST_FOUNDATION.clear()
        _LAST_FOUNDATION.update(foundation)
        return payload
    except DecisionPayloadValidationError as exc:
        _payload_validation_failure(exc)
    finally:
        if store is not None:
            store.close()


@app.post("/api/v1/what-if")
def what_if(req: WhatIfRequest):
    if not _LAST_FOUNDATION:
        _error("NOT_FOUND", "no run yet — POST /api/v1/run first", status=404)
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
                _error("NOT_FOUND", f"run {run_id} not found", status=404)
            return payload
        payload = store.latest_run()
        if payload is None:
            _error("NOT_FOUND", "no run yet", status=404)
        return payload
    finally:
        store.close()


@app.get("/api/v1/holdings/{instrument}")
def holding(instrument: str, run_id: str | None = None):
    """One holding's full decision. `run_id` selects a past run; default = latest."""
    store = RunStore()
    try:
        if run_id:
            payload = store.get_run(run_id)
            if payload is None:
                _error("NOT_FOUND", f"run {run_id} not found", status=404)
        else:
            payload = store.latest_run()
            if payload is None:
                _error("NOT_FOUND", "no run yet", status=404)
        for h in payload["holdings"]:
            if h["instrument"] == instrument or h.get("ticker") == instrument:
                return h
        _error("NOT_FOUND", f"no holding {instrument!r} in run {payload['run_id']}",
               status=404)
    finally:
        store.close()


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
            _error("NOT_FOUND", f"run {run_id} not found", status=404)
        return d
    finally:
        store.close()


@app.get("/api/v1/tax-tracker")
def tax_tracker(fy: str = "2026-27"):
    if not _FY_RE.match(fy or ""):
        _error("VALIDATION_ERROR",
               f"fy must look like an Indian financial year (YYYY-YY), got {fy!r}",
               status=422)
    if not _LAST_TAX:
        _error("NOT_FOUND",
               "no realised-gains data — POST /api/v1/run with a sold.csv to compute "
               "the tax year", status=404)
    available = _LAST_TAX.get("fy")
    if available and available != fy:
        _error("NOT_FOUND",
               f"tax year {fy!r} has not been computed — the loaded sold ledger "
               f"produced FY {available!r}. Re-run with a sold ledger covering {fy}.",
               status=404, details={"available_fy": available})
    return _LAST_TAX


@app.get("/api/v1/policy")
def get_policy():
    from .policy import load_policy
    return load_policy()


@app.put("/api/v1/policy")
def put_policy(body: dict):
    """Validate and commit policy to the app-managed data directory.

    Never writes the shipped, signed `policy/policy.yaml`. Unknown keys are
    rejected, so a malformed request cannot inject arbitrary policy values.
    """
    from .policy import commit_policy, load_policy, validate_policy

    current = load_policy()
    merged = {**current, **body}
    if body.get("weights"):
        merged["weights"] = {**current.get("weights", {}), **body["weights"]}
    errors = validate_policy(merged)
    if errors:
        _error("POLICY_INVALID", "policy rejected", status=422,
               details={"violations": errors})
    merged["policy_version"] = int(current.get("policy_version", 0)) + 1
    return commit_policy(merged)


@app.post("/api/v1/policy/reset")
def reset_policy_endpoint():
    """Discard user overrides and return to the shipped signed defaults."""
    from .policy import reset_policy
    return reset_policy()
