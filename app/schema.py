"""Runtime DecisionPayload v1 structural validation (CR-001).

This module is deliberately validation-only. It does not compute, coerce,
normalise, or repair payloads; it only checks the known shipped v1 contract while
allowing unknown/extra fields for forward compatibility and historical records.
"""
from __future__ import annotations

from math import isfinite
from numbers import Real
from typing import Any


DECISIONS = {"HOLD", "WATCH", "TRIM", "HARVEST", "EXIT", "NO-DECISION"}
OPPORTUNITY_COST_SOURCES = {"peg_proxy", "watchlist", "missing"}
SUBSCORE_KEYS = (
    "position_sizing",
    "valuation_stretch",
    "quality_drift",
    "tax_efficiency",
    "opportunity_cost",
    "technical_regime",
)


class DecisionPayloadValidationError(ValueError):
    """Raised when a DecisionPayload v1 object fails structural validation."""

    def __init__(self, errors: list[str]):
        self.errors = tuple(errors)
        preview = "; ".join(errors[:5])
        if len(errors) > 5:
            preview += f"; ... ({len(errors)} total errors)"
        super().__init__(f"DecisionPayload v1 validation failed: {preview}")


def validate_decision_payload(payload: Any) -> Any:
    """Validate a DecisionPayload v1 object and return it unchanged.

    Validation is deterministic, read-only, non-coercing, and intentionally
    permissive about unknown/extra fields. Existing v1 nullability is preserved,
    including NO-DECISION holdings and optional tax_year payloads.
    """
    errors: list[str] = []
    _validate_payload(payload, "$", errors)
    if errors:
        raise DecisionPayloadValidationError(errors)
    return payload


# ---- primitive checks -------------------------------------------------------


def _is_mapping(value: Any) -> bool:
    return isinstance(value, dict)


def _is_sequence(value: Any) -> bool:
    return isinstance(value, (list, tuple))


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and isfinite(float(value))


def _add(errors: list[str], path: str, message: str) -> None:
    errors.append(f"{path}: {message}")


def _require(mapping: Any, path: str, fields: tuple[str, ...] | list[str], errors: list[str]) -> None:
    if not _is_mapping(mapping):
        _add(errors, path, "expected object")
        return
    for field in fields:
        if field not in mapping:
            _add(errors, f"{path}.{field}", "missing required field")


def _string(value: Any, path: str, errors: list[str], nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str):
        _add(errors, path, "expected string" + (" or null" if nullable else ""))


def _boolean(value: Any, path: str, errors: list[str]) -> None:
    if not _is_bool(value):
        _add(errors, path, "expected boolean")


def _integer(value: Any, path: str, errors: list[str], nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not _is_int(value):
        _add(errors, path, "expected integer" + (" or null" if nullable else ""))


def _number(value: Any, path: str, errors: list[str], nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not _is_number(value):
        _add(errors, path, "expected finite number" + (" or null" if nullable else ""))


def _number_range(
    value: Any,
    path: str,
    errors: list[str],
    low: float,
    high: float,
    nullable: bool = False,
    integer: bool = False,
) -> None:
    if value is None and nullable:
        return
    if integer:
        if not _is_int(value):
            _add(errors, path, f"expected integer in range {low:g}..{high:g}" + (" or null" if nullable else ""))
            return
    elif not _is_number(value):
        _add(errors, path, f"expected finite number in range {low:g}..{high:g}" + (" or null" if nullable else ""))
        return
    if not (low <= float(value) <= high):
        _add(errors, path, f"expected value in range {low:g}..{high:g}")


def _list(value: Any, path: str, errors: list[str]) -> bool:
    if not _is_sequence(value):
        _add(errors, path, "expected array")
        return False
    return True


def _list_of_strings(value: Any, path: str, errors: list[str]) -> None:
    if not _list(value, path, errors):
        return
    for i, item in enumerate(value):
        _string(item, f"{path}[{i}]", errors)


def _number_map(value: Any, path: str, errors: list[str]) -> None:
    if not _is_mapping(value):
        _add(errors, path, "expected object with numeric values")
        return
    for key, item in value.items():
        if not isinstance(key, str):
            _add(errors, f"{path}.{key!r}", "expected string key")
        _number(item, f"{path}.{key}", errors)


# ---- top-level payload ------------------------------------------------------


def _validate_payload(payload: Any, path: str, errors: list[str]) -> None:
    required = (
        "run_id",
        "as_of",
        "engine_version",
        "policy_version",
        "input_hash",
        "content_hash",
        "provenance",
        "portfolio_summary",
        "holdings",
        "portfolio_layer",
        "warnings",
    )
    _require(payload, path, required, errors)
    if not _is_mapping(payload):
        return

    _string(payload.get("run_id"), f"{path}.run_id", errors)
    _string(payload.get("as_of"), f"{path}.as_of", errors)
    _string(payload.get("engine_version"), f"{path}.engine_version", errors)
    _integer(payload.get("policy_version"), f"{path}.policy_version", errors)
    _string(payload.get("input_hash"), f"{path}.input_hash", errors)
    _string(payload.get("content_hash"), f"{path}.content_hash", errors)
    _validate_provenance(payload.get("provenance"), f"{path}.provenance", errors)
    _validate_portfolio_summary(payload.get("portfolio_summary"), f"{path}.portfolio_summary", errors)
    _validate_holdings(payload.get("holdings"), f"{path}.holdings", errors)
    _validate_portfolio_layer(payload.get("portfolio_layer"), f"{path}.portfolio_layer", errors)
    _validate_warnings(payload.get("warnings"), f"{path}.warnings", errors)
    if "tax_year" in payload:
        _validate_tax_year(payload.get("tax_year"), f"{path}.tax_year", errors)


def _validate_provenance(value: Any, path: str, errors: list[str]) -> None:
    _require(value, path, ("engine_version", "normalization_version", "calculation_version", "policy_version", "sources"), errors)
    if not _is_mapping(value):
        return
    _string(value.get("engine_version"), f"{path}.engine_version", errors)
    _string(value.get("normalization_version"), f"{path}.normalization_version", errors)
    _string(value.get("calculation_version"), f"{path}.calculation_version", errors)
    _integer(value.get("policy_version"), f"{path}.policy_version", errors)
    sources = value.get("sources")
    if not _is_mapping(sources):
        _add(errors, f"{path}.sources", "expected object")
        return
    for name, source in sources.items():
        spath = f"{path}.sources.{name}"
        _require(source, spath, ("as_of", "days_behind"), errors)
        if _is_mapping(source):
            _string(source.get("as_of"), f"{spath}.as_of", errors)
            _number(source.get("days_behind"), f"{spath}.days_behind", errors)
            # CR-022 / F2-D3 (additive, optional): dual-timestamp labels.
            if "as_of_source" in source:
                _string(source.get("as_of_source"), f"{spath}.as_of_source", errors)
            if "declared_source_as_of" in source:
                _string(source.get("declared_source_as_of"), f"{spath}.declared_source_as_of",
                        errors, nullable=True)
    # CR-022 / F2-D4 (additive, optional): snapshot-archive identity block.
    if "archive" in value:
        _validate_archive_provenance(value.get("archive"), f"{path}.archive", errors)


def _sha256_hex(value: Any, path: str, errors: list[str]) -> None:
    if not (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value)):
        _add(errors, path, "expected 64-char lowercase hex SHA-256")


def _validate_archive_provenance(value: Any, path: str, errors: list[str]) -> None:
    if value is None:
        return  # legacy foundations carry no archive identity
    _require(value, path, ("archive_version", "manifest",
                           "foundation_sha256", "policy_sha256"), errors)
    if not _is_mapping(value):
        return
    _integer(value.get("archive_version"), f"{path}.archive_version", errors)
    _string(value.get("manifest"), f"{path}.manifest", errors)
    # raw_sha256 (per-file received-byte hashes) is optional forward-compat:
    # shipped payloads identify raw evidence via the manifest (run_id linkage).
    if "raw_sha256" in value:
        raw = value.get("raw_sha256")
        if not _is_mapping(raw):
            _add(errors, f"{path}.raw_sha256", "expected object")
        else:
            for slot, sha in raw.items():
                _sha256_hex(sha, f"{path}.raw_sha256.{slot}", errors)
    _sha256_hex(value.get("foundation_sha256"), f"{path}.foundation_sha256", errors)
    _sha256_hex(value.get("policy_sha256"), f"{path}.policy_sha256", errors)
    # CR-023 (additive, optional): authority theme-document integrity hash.
    if "themes_sha256" in value:
        _sha256_hex(value.get("themes_sha256"), f"{path}.themes_sha256", errors)


def _validate_portfolio_summary(value: Any, path: str, errors: list[str]) -> None:
    _require(value, path, ("total_value", "holdings_count", "decision_distribution", "stage1_gates_fired", "tax"), errors)
    if not _is_mapping(value):
        return
    _number(value.get("total_value"), f"{path}.total_value", errors)
    _integer(value.get("holdings_count"), f"{path}.holdings_count", errors)
    _integer(value.get("stage1_gates_fired"), f"{path}.stage1_gates_fired", errors)
    dist = value.get("decision_distribution")
    if not _is_mapping(dist):
        _add(errors, f"{path}.decision_distribution", "expected object")
    else:
        for decision, count in dist.items():
            if not isinstance(decision, str):
                _add(errors, f"{path}.decision_distribution.{decision!r}", "expected string decision key")
            elif decision not in DECISIONS:
                _add(errors, f"{path}.decision_distribution.{decision}", "expected known decision key")
            _integer(count, f"{path}.decision_distribution.{decision}", errors)
    _validate_tax_summary_block(value.get("tax"), f"{path}.tax", errors)


def _validate_tax_summary_block(value: Any, path: str, errors: list[str]) -> None:
    if not _is_mapping(value):
        _add(errors, path, "expected object")
        return
    if "fy" in value:
        _string(value.get("fy"), f"{path}.fy", errors, nullable=True)
    if "provisional" in value:
        _boolean(value.get("provisional"), f"{path}.provisional", errors)
    for key in ("ltcg_booked", "ltcg_exemption", "ltcg_headroom", "stcg_booked", "stcl_harvestable"):
        if key in value:
            _number(value.get(key), f"{path}.{key}", errors)
    if "note" in value:
        _string(value.get("note"), f"{path}.note", errors)


# ---- holdings ---------------------------------------------------------------


def _validate_holdings(value: Any, path: str, errors: list[str]) -> None:
    if not _list(value, path, errors):
        return
    for i, holding in enumerate(value):
        _validate_holding(holding, f"{path}[{i}]", errors)


def _validate_holding(value: Any, path: str, errors: list[str]) -> None:
    common = (
        "instrument",
        "ticker",
        "bucket",
        "decision",
        "composite_score",
        "confidence",
        "confidence_breakdown",
        "subscores",
        "stage1",
        "evidence",
        "primary_drivers",
        "watch_flags",
        "behavioral_flags",
        "trim",
        "tax_status",
        "reason_tree",
        "why_now",
        "previous_run",
        "next_review_date",
    )
    _require(value, path, common, errors)
    if not _is_mapping(value):
        return

    decision = value.get("decision")
    _string(value.get("instrument"), f"{path}.instrument", errors)
    _string(value.get("ticker"), f"{path}.ticker", errors, nullable=True)
    _string(value.get("bucket"), f"{path}.bucket", errors, nullable=True)
    if "bucket_basis" in value:
        _string(value.get("bucket_basis"), f"{path}.bucket_basis", errors)
    if "band_basis" in value:
        _string(value.get("band_basis"), f"{path}.band_basis", errors)
    if decision not in DECISIONS:
        _add(errors, f"{path}.decision", f"expected one of {sorted(DECISIONS)}")
    _number_range(value.get("composite_score"), f"{path}.composite_score", errors, 0, 100, nullable=True)
    _number_range(value.get("confidence"), f"{path}.confidence", errors, 20, 95, nullable=True, integer=True)
    _validate_confidence_breakdown(value.get("confidence_breakdown"), f"{path}.confidence_breakdown", errors)
    _validate_subscores(value.get("subscores"), f"{path}.subscores", errors)
    _validate_stage1(value.get("stage1"), f"{path}.stage1", errors)
    _validate_evidence(value.get("evidence"), f"{path}.evidence", errors)
    _list_of_strings(value.get("primary_drivers"), f"{path}.primary_drivers", errors)
    _list_of_strings(value.get("watch_flags"), f"{path}.watch_flags", errors)
    _list_of_strings(value.get("behavioral_flags"), f"{path}.behavioral_flags", errors)
    _validate_trim(value.get("trim"), f"{path}.trim", errors)
    _validate_tax_status(value.get("tax_status"), f"{path}.tax_status", errors)
    _validate_reason_tree(value.get("reason_tree"), f"{path}.reason_tree", errors)
    _validate_why_now(value.get("why_now"), f"{path}.why_now", errors)
    _validate_previous_run(value.get("previous_run"), f"{path}.previous_run", errors)
    _string(value.get("next_review_date"), f"{path}.next_review_date", errors, nullable=True)

    if decision != "NO-DECISION":
        full_fields = (
            "alloc_pct",
            "gain_pct",
            "current_value",
            "qty_held",
            "pledge_pct",
            "data_completeness",
            "data_quality",
            "lots",
            "behavioral",
        )
        _require(value, path, full_fields, errors)

    for key in ("alloc_pct", "gain_pct", "current_value", "qty_held", "pledge_pct"):
        if key in value:
            _number(value.get(key), f"{path}.{key}", errors, nullable=True)
    if "data_completeness" in value:
        _validate_bool_map(value.get("data_completeness"), f"{path}.data_completeness", errors)
    if "data_quality" in value:
        _validate_string_map(value.get("data_quality"), f"{path}.data_quality", errors)
    if "lots" in value:
        _validate_lots(value.get("lots"), f"{path}.lots", errors)
    if "behavioral" in value:
        _validate_behavioral(value.get("behavioral"), f"{path}.behavioral", errors)


def _validate_confidence_breakdown(value: Any, path: str, errors: list[str]) -> None:
    if value is None:
        return
    if not _is_mapping(value):
        _add(errors, path, "expected object or null")
        return
    for key, item in value.items():
        if not isinstance(key, str):
            _add(errors, f"{path}.{key!r}", "expected string key")
        _number(item, f"{path}.{key}", errors)


def _validate_subscores(value: Any, path: str, errors: list[str]) -> None:
    if value is None:
        return
    _require(value, path, SUBSCORE_KEYS, errors)
    if not _is_mapping(value):
        return
    for key in SUBSCORE_KEYS:
        if key in value:
            _number_range(value.get(key), f"{path}.{key}", errors, 0, 100, nullable=True)


def _validate_stage1(value: Any, path: str, errors: list[str]) -> None:
    _require(value, path, ("fired", "gates_fired", "winning_gate", "tax_defer_suppressed"), errors)
    if not _is_mapping(value):
        return
    _boolean(value.get("fired"), f"{path}.fired", errors)
    _list_of_strings(value.get("gates_fired"), f"{path}.gates_fired", errors)
    _string(value.get("winning_gate"), f"{path}.winning_gate", errors, nullable=True)
    _boolean(value.get("tax_defer_suppressed"), f"{path}.tax_defer_suppressed", errors)


def _validate_evidence(value: Any, path: str, errors: list[str]) -> None:
    if value is None:
        return
    _require(value, path, ("coverage", "tier", "missing_weight", "critical_categories_missing"), errors)
    if not _is_mapping(value):
        return
    _number(value.get("coverage"), f"{path}.coverage", errors)
    _string(value.get("tier"), f"{path}.tier", errors)
    _number(value.get("missing_weight"), f"{path}.missing_weight", errors)
    _list_of_strings(value.get("critical_categories_missing"), f"{path}.critical_categories_missing", errors)
    if "decision_cap" in value:
        _string(value.get("decision_cap"), f"{path}.decision_cap", errors, nullable=True)


def _validate_trim(value: Any, path: str, errors: list[str]) -> None:
    if value is None:
        return
    _require(value, path, ("mode", "suggested_qty", "suggested_value", "fifo_lots_to_sell", "tax_breakdown", "est_transaction_cost"), errors)
    if not _is_mapping(value):
        return
    if value.get("mode") not in {"S", "V"}:
        _add(errors, f"{path}.mode", "expected 'S' or 'V'")
    _number(value.get("suggested_qty"), f"{path}.suggested_qty", errors, nullable=True)
    _number(value.get("suggested_value"), f"{path}.suggested_value", errors, nullable=True)
    if not _list(value.get("fifo_lots_to_sell"), f"{path}.fifo_lots_to_sell", errors):
        pass
    else:
        for i, item in enumerate(value.get("fifo_lots_to_sell")):
            _validate_fifo_lot(item, f"{path}.fifo_lots_to_sell[{i}]", errors)
    tb = value.get("tax_breakdown")
    _require(tb, f"{path}.tax_breakdown", ("stcg_gain", "ltcg_gain", "stcg_tax", "ltcg_tax", "realized_loss"), errors)
    if _is_mapping(tb):
        for key in ("stcg_gain", "ltcg_gain", "stcg_tax", "ltcg_tax", "realized_loss"):
            if key in tb:
                _number(tb.get(key), f"{path}.tax_breakdown.{key}", errors)
    _number(value.get("est_transaction_cost"), f"{path}.est_transaction_cost", errors)
    for key in ("alloc_after_pct", "target_alloc_pct", "rho"):
        if key in value:
            _number(value.get(key), f"{path}.{key}", errors)
    if "participation_capped" in value:
        _boolean(value.get("participation_capped"), f"{path}.participation_capped", errors)


def _validate_fifo_lot(value: Any, path: str, errors: list[str]) -> None:
    _require(value, path, ("lot_id", "qty"), errors)
    if not _is_mapping(value):
        return
    _integer(value.get("lot_id"), f"{path}.lot_id", errors)
    _number(value.get("qty"), f"{path}.qty", errors)


def _validate_tax_status(value: Any, path: str, errors: list[str]) -> None:
    if value is None:
        return
    _require(value, path, ("mixed_ltcg", "oldest_lot_days_to_ltcg", "ltcg_eligible_lots"), errors)
    if not _is_mapping(value):
        return
    _boolean(value.get("mixed_ltcg"), f"{path}.mixed_ltcg", errors)
    _integer(value.get("oldest_lot_days_to_ltcg"), f"{path}.oldest_lot_days_to_ltcg", errors, nullable=True)
    _integer(value.get("ltcg_eligible_lots"), f"{path}.ltcg_eligible_lots", errors)


def _validate_reason_tree(value: Any, path: str, errors: list[str]) -> None:
    _require(value, path, ("decision_path",), errors)
    if not _is_mapping(value):
        return
    _string(value.get("decision_path"), f"{path}.decision_path", errors)
    # reason_tree stage structures are intentionally flexible v1 records.
    for key in ("stage1", "stage2"):
        if key in value and not _is_mapping(value.get(key)):
            _add(errors, f"{path}.{key}", "expected object")
    stage2 = value.get("stage2")
    if _is_mapping(stage2) and "opportunity_cost" in stage2:
        _validate_opportunity_cost_evidence(stage2.get("opportunity_cost"), f"{path}.stage2.opportunity_cost", errors)


def _validate_opportunity_cost_evidence(value: Any, path: str, errors: list[str]) -> None:
    _require(value, path, ("source",), errors)
    if not _is_mapping(value):
        return
    source = value.get("source")
    if source not in OPPORTUNITY_COST_SOURCES:
        _add(errors, f"{path}.source", f"expected one of {sorted(OPPORTUNITY_COST_SOURCES)}")
    if "score" in value:
        _number_range(value.get("score"), f"{path}.score", errors, 0, 100, nullable=True)


def _validate_why_now(value: Any, path: str, errors: list[str]) -> None:
    _require(value, path, ("primary_trigger",), errors)
    if not _is_mapping(value):
        return
    _string(value.get("primary_trigger"), f"{path}.primary_trigger", errors)
    if "contributors" in value:
        if not _list(value.get("contributors"), f"{path}.contributors", errors):
            return
        for i, item in enumerate(value.get("contributors")):
            ipath = f"{path}.contributors[{i}]"
            _require(item, ipath, ("label", "value", "weight"), errors)
            if _is_mapping(item):
                _string(item.get("label"), f"{ipath}.label", errors)
                _number(item.get("value"), f"{ipath}.value", errors)
                _number(item.get("weight"), f"{ipath}.weight", errors)


def _validate_previous_run(value: Any, path: str, errors: list[str]) -> None:
    if value is None:
        return
    _require(value, path, ("decision", "composite_score", "as_of"), errors)
    if not _is_mapping(value):
        return
    if value.get("decision") not in DECISIONS:
        _add(errors, f"{path}.decision", f"expected one of {sorted(DECISIONS)}")
    _number_range(value.get("composite_score"), f"{path}.composite_score", errors, 0, 100, nullable=True)
    _string(value.get("as_of"), f"{path}.as_of", errors)


def _validate_bool_map(value: Any, path: str, errors: list[str]) -> None:
    if not _is_mapping(value):
        _add(errors, path, "expected object with boolean values")
        return
    for key, item in value.items():
        if not isinstance(key, str):
            _add(errors, f"{path}.{key!r}", "expected string key")
        _boolean(item, f"{path}.{key}", errors)


def _validate_string_map(value: Any, path: str, errors: list[str]) -> None:
    if not _is_mapping(value):
        _add(errors, path, "expected object with string values")
        return
    for key, item in value.items():
        if not isinstance(key, str):
            _add(errors, f"{path}.{key!r}", "expected string key")
        _string(item, f"{path}.{key}", errors)


def _validate_lots(value: Any, path: str, errors: list[str]) -> None:
    if not _list(value, path, errors):
        return
    for i, item in enumerate(value):
        ipath = f"{path}[{i}]"
        _require(
            item,
            ipath,
            (
                "lot_id",
                "instrument",
                "ticker",
                "trade_date",
                "qty",
                "buy_price",
                "ltp",
                "invested",
                "value",
                "pnl",
                "pnl_pct",
                "days_held",
                "days_to_ltcg",
                "ltcg_eligible",
            ),
            errors,
        )
        if not _is_mapping(item):
            continue
        _integer(item.get("lot_id"), f"{ipath}.lot_id", errors)
        _string(item.get("instrument"), f"{ipath}.instrument", errors)
        _string(item.get("ticker"), f"{ipath}.ticker", errors, nullable=True)
        _string(item.get("trade_date"), f"{ipath}.trade_date", errors)
        _number(item.get("qty"), f"{ipath}.qty", errors)
        _number(item.get("buy_price"), f"{ipath}.buy_price", errors)
        _number(item.get("ltp"), f"{ipath}.ltp", errors)
        _number(item.get("invested"), f"{ipath}.invested", errors, nullable=True)
        _number(item.get("value"), f"{ipath}.value", errors, nullable=True)
        _number(item.get("pnl"), f"{ipath}.pnl", errors, nullable=True)
        _number(item.get("pnl_pct"), f"{ipath}.pnl_pct", errors, nullable=True)
        _integer(item.get("days_held"), f"{ipath}.days_held", errors)
        _integer(item.get("days_to_ltcg"), f"{ipath}.days_to_ltcg", errors)
        _boolean(item.get("ltcg_eligible"), f"{ipath}.ltcg_eligible", errors)


def _validate_behavioral(value: Any, path: str, errors: list[str]) -> None:
    _require(value, path, ("flag", "requires_reunderwrite", "blocks_adds"), errors)
    if not _is_mapping(value):
        return
    _string(value.get("flag"), f"{path}.flag", errors)
    _boolean(value.get("requires_reunderwrite"), f"{path}.requires_reunderwrite", errors)
    _boolean(value.get("blocks_adds"), f"{path}.blocks_adds", errors)


# ---- portfolio layer --------------------------------------------------------


def _validate_portfolio_layer(value: Any, path: str, errors: list[str]) -> None:
    _require(value, path, ("action_queue", "theme_concentration", "tax_sequencing"), errors)
    if not _is_mapping(value):
        return
    _validate_action_queue(value.get("action_queue"), f"{path}.action_queue", errors)
    _validate_theme_concentration(value.get("theme_concentration"), f"{path}.theme_concentration", errors)
    _validate_tax_sequencing(value.get("tax_sequencing"), f"{path}.tax_sequencing", errors)


def _validate_action_queue(value: Any, path: str, errors: list[str]) -> None:
    if not _list(value, path, errors):
        return
    for i, item in enumerate(value):
        ipath = f"{path}[{i}]"
        _require(item, ipath, ("rank", "instrument", "decision", "reason", "score"), errors)
        if not _is_mapping(item):
            continue
        _integer(item.get("rank"), f"{ipath}.rank", errors)
        _string(item.get("instrument"), f"{ipath}.instrument", errors)
        if item.get("decision") not in DECISIONS:
            _add(errors, f"{ipath}.decision", f"expected one of {sorted(DECISIONS)}")
        _string(item.get("reason"), f"{ipath}.reason", errors)
        _number_range(item.get("score"), f"{ipath}.score", errors, 0, 100, nullable=True)


def _validate_theme_concentration(value: Any, path: str, errors: list[str]) -> None:
    if not _list(value, path, errors):
        return
    for i, item in enumerate(value):
        ipath = f"{path}[{i}]"
        _require(item, ipath, ("theme", "alloc_pct", "status"), errors)
        if not _is_mapping(item):
            continue
        _string(item.get("theme"), f"{ipath}.theme", errors)
        _number(item.get("alloc_pct"), f"{ipath}.alloc_pct", errors)
        _string(item.get("status"), f"{ipath}.status", errors)
        # CR-023 (additive, optional): grouping provenance label.
        if "source" in item:
            src = item.get("source")
            if src not in ("manual", "fallback_sub_sector"):
                _add(errors, f"{ipath}.source",
                     "expected 'manual' or 'fallback_sub_sector'")


def _validate_tax_sequencing(value: Any, path: str, errors: list[str]) -> None:
    if not _list(value, path, errors):
        return
    for i, item in enumerate(value):
        ipath = f"{path}[{i}]"
        _require(item, ipath, ("instrument", "decision", "ltcg_gain", "stcg_gain", "est_tax_if_realised"), errors)
        if not _is_mapping(item):
            continue
        _string(item.get("instrument"), f"{ipath}.instrument", errors)
        if item.get("decision") not in DECISIONS:
            _add(errors, f"{ipath}.decision", f"expected one of {sorted(DECISIONS)}")
        _number(item.get("ltcg_gain"), f"{ipath}.ltcg_gain", errors)
        _number(item.get("stcg_gain"), f"{ipath}.stcg_gain", errors)
        _number(item.get("est_tax_if_realised"), f"{ipath}.est_tax_if_realised", errors)


# ---- warnings and tax_year --------------------------------------------------


def _validate_warnings(value: Any, path: str, errors: list[str]) -> None:
    if not _list(value, path, errors):
        return
    for i, item in enumerate(value):
        ipath = f"{path}[{i}]"
        _require(item, ipath, ("code", "message"), errors)
        if not _is_mapping(item):
            continue
        _string(item.get("code"), f"{ipath}.code", errors)
        _string(item.get("message"), f"{ipath}.message", errors)
        if "instrument" in item:
            _string(item.get("instrument"), f"{ipath}.instrument", errors, nullable=True)


def _validate_tax_year(value: Any, path: str, errors: list[str]) -> None:
    _require(value, path, ("realized", "summary", "open_positions"), errors)
    if not _is_mapping(value):
        return
    _validate_realized(value.get("realized"), f"{path}.realized", errors)
    _validate_tax_year_summary(value.get("summary"), f"{path}.summary", errors)
    open_positions = value.get("open_positions")
    if not _is_mapping(open_positions):
        _add(errors, f"{path}.open_positions", "expected object")
    else:
        for instrument, split in open_positions.items():
            spath = f"{path}.open_positions.{instrument}"
            if not isinstance(instrument, str):
                _add(errors, f"{path}.open_positions.{instrument!r}", "expected string key")
            _number_map(split, spath, errors)


def _validate_realized(value: Any, path: str, errors: list[str]) -> None:
    if not _list(value, path, errors):
        return
    for i, item in enumerate(value):
        ipath = f"{path}[{i}]"
        _require(item, ipath, ("instrument", "lot_id", "sell_date", "qty", "buy_price", "sell_price", "gain", "holding_days", "type"), errors)
        if not _is_mapping(item):
            continue
        _string(item.get("instrument"), f"{ipath}.instrument", errors)
        _integer(item.get("lot_id"), f"{ipath}.lot_id", errors)
        _string(item.get("sell_date"), f"{ipath}.sell_date", errors)
        _number(item.get("qty"), f"{ipath}.qty", errors)
        _number(item.get("buy_price"), f"{ipath}.buy_price", errors)
        _number(item.get("sell_price"), f"{ipath}.sell_price", errors)
        _number(item.get("gain"), f"{ipath}.gain", errors)
        _integer(item.get("holding_days"), f"{ipath}.holding_days", errors)
        _string(item.get("type"), f"{ipath}.type", errors)


def _validate_tax_year_summary(value: Any, path: str, errors: list[str]) -> None:
    _require(value, path, ("fy", "gross", "set_off", "net", "exemption", "taxable", "tax", "carry_forward_out"), errors)
    if not _is_mapping(value):
        return
    _string(value.get("fy"), f"{path}.fy", errors, nullable=True)
    for key in ("gross", "set_off", "net", "taxable", "tax"):
        if key in value:
            _number_map(value.get(key), f"{path}.{key}", errors)
    exemption = value.get("exemption")
    _require(exemption, f"{path}.exemption", ("used", "headroom"), errors)
    if _is_mapping(exemption):
        _number(exemption.get("used"), f"{path}.exemption.used", errors)
        _number(exemption.get("headroom"), f"{path}.exemption.headroom", errors)
    carry = value.get("carry_forward_out")
    _require(carry, f"{path}.carry_forward_out", ("ltcl", "stcl"), errors)
    if _is_mapping(carry):
        for key in ("ltcl", "stcl"):
            if key not in carry:
                continue
            if not _list(carry.get(key), f"{path}.carry_forward_out.{key}", errors):
                continue
            for i, entry in enumerate(carry.get(key)):
                epath = f"{path}.carry_forward_out.{key}[{i}]"
                if not _is_sequence(entry) or len(entry) != 2:
                    _add(errors, epath, "expected [amount, age] pair")
                    continue
                _number(entry[0], f"{epath}[0]", errors)
                _integer(entry[1], f"{epath}[1]", errors)
