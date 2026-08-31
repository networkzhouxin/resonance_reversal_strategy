"""Fail-closed real-path comparison for the volume-ratio buy candidate."""

import argparse
from datetime import date
import hashlib
import importlib.util
import math
import pathlib
import statistics


BASELINE_BUILD = "20260828.5"
CANDIDATE_BUILD = "20260831.1"
EXPECTED_ATR_POLICY = "OBSERVE_ONLY"
EXPECTED_RELATIVE_BUY_POLICY = "EMPTY_SLOT_BACKFILL"
EXPECTED_VOLUME_POLICY = "T1_VOLUME_RATIO_AT_OR_BELOW_ONE"
EXPECTED_VOLUME_THRESHOLD = 1.0
INITIAL_CAPITAL = 20000.0
EVALUATION_YEARS = (2019, 2020, 2021)


def _load_risk_analyzer(module_name, expected_build):
    path = pathlib.Path(__file__).with_name(
        "analyze_resonance_trade_risk.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.EXPECTED_BUILD = expected_build
    return module


BASELINE_RISK = _load_risk_analyzer(
    "_resonance_volume_baseline_risk", BASELINE_BUILD,
)
CANDIDATE_RISK = _load_risk_analyzer(
    "_resonance_volume_candidate_risk", CANDIDATE_BUILD,
)


def _finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be finite" % label)
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("%s must be finite" % label)
    return result


def _source_file_report(paths):
    result = []
    for path in sorted(
            pathlib.Path(value).expanduser().resolve(strict=True)
            for value in paths):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        result.append({"path": str(path), "sha256": digest})
    return result


def _candidate_identity(record, role):
    if record.get("new_buy_volume_policy") != EXPECTED_VOLUME_POLICY:
        raise ValueError("%s new_buy_volume_policy mismatch" % role)
    try:
        threshold = _finite(
            record.get("new_buy_volume_threshold"),
            "%s new_buy_volume_threshold" % role,
        )
    except ValueError as exc:
        raise ValueError(
            "%s new_buy_volume_threshold mismatch" % role
        ) from exc
    if threshold != EXPECTED_VOLUME_THRESHOLD:
        raise ValueError("%s new_buy_volume_threshold mismatch" % role)


def _signal_snapshots(records):
    result = {}
    for record in records:
        if record.get("event") != "signal_snapshot":
            continue
        timestamp = record.get("_timestamp")
        code = record.get("code")
        if timestamp is None or not isinstance(code, str):
            continue
        key = (timestamp.date(), code)
        if key in result:
            raise ValueError("duplicate signal snapshot")
        result[key] = record
    return result


def _candidate_volume_decisions(parsed, role, sessions):
    previous_session = {
        current: previous for previous, current in zip(sessions, sessions[1:])
    }
    rejection_records = {}
    for record in parsed.records:
        if record.get("event") != "resonance_decision":
            continue
        reason = record.get("reason")
        if reason not in (
                "BUY_VOLUME_RATIO_ABOVE_ONE", "BUY_VOLUME_RATIO_INVALID"):
            continue
        key = (
            record["_timestamp"].date(), record.get("code"),
            record.get("resonance_id"), reason,
        )
        if key in rejection_records or record.get("accepted") is not False:
            raise ValueError("%s volume rejection is invalid" % role)
        rejection_records[key] = record

    decisions = {}
    for record in parsed.records:
        if record.get("event") != "new_buy_volume_eligibility":
            continue
        timestamp = record.get("_timestamp")
        code = record.get("code")
        resonance_id = record.get("resonance_id")
        entry_source = record.get("entry_source")
        eligibility = record.get("eligibility")
        try:
            threshold = _finite(
                record.get("threshold"), "%s volume audit threshold" % role,
            )
        except ValueError as exc:
            raise ValueError(
                "%s volume eligibility audit is invalid" % role
            ) from exc
        if (record.get("build") != CANDIDATE_BUILD
                or record.get("policy") != EXPECTED_VOLUME_POLICY
                or threshold != EXPECTED_VOLUME_THRESHOLD
                or timestamp is None or not isinstance(code, str) or not code
                or not isinstance(resonance_id, str) or not resonance_id
                or entry_source not in ("FORMAL", "RELATIVE")
                or eligibility not in (
                    "ELIGIBLE", "ABOVE_ONE", "INVALID_VALUE",
                )
                or record.get("decision_date")
                != timestamp.date().isoformat()
                or not isinstance(record.get("signal_date"), str)):
            raise ValueError("%s volume eligibility audit is invalid" % role)
        try:
            signal_date = date.fromisoformat(record["signal_date"])
        except ValueError as exc:
            raise ValueError(
                "%s volume eligibility audit is invalid" % role
            ) from exc
        if previous_session.get(timestamp.date()) != signal_date:
            raise ValueError(
                "%s volume eligibility signal date is not T-1" % role
            )
        expected_source = (
            "RELATIVE" if resonance_id.startswith("RELATIVE:") else "FORMAL"
        )
        if entry_source != expected_source:
            raise ValueError("%s volume eligibility source mismatch" % role)
        value = record.get("volume_ratio")
        if eligibility == "INVALID_VALUE":
            if value is not None:
                raise ValueError("%s invalid volume audit has a value" % role)
            expected_reason = "BUY_VOLUME_RATIO_INVALID"
            normalized_value = None
        else:
            normalized_value = _finite(value, "%s volume audit value" % role)
            if normalized_value < 0:
                raise ValueError("%s volume audit value is negative" % role)
            if eligibility == "ELIGIBLE":
                if normalized_value > EXPECTED_VOLUME_THRESHOLD:
                    raise ValueError("%s eligible volume audit is above one" % role)
                expected_reason = None
            else:
                if normalized_value <= EXPECTED_VOLUME_THRESHOLD:
                    raise ValueError("%s above-one volume audit is invalid" % role)
                expected_reason = "BUY_VOLUME_RATIO_ABOVE_ONE"
        key = (timestamp.date(), code, resonance_id)
        if key in decisions:
            raise ValueError("%s duplicate volume eligibility audit" % role)
        if expected_reason is not None:
            rejection = rejection_records.get(key + (expected_reason,))
            if (rejection is None
                    or record.get("_ordinal") >= rejection.get("_ordinal")):
                raise ValueError("%s volume rejection audit is missing" % role)
        decisions[key] = {
            "record": record,
            "identity": (
                timestamp.date().isoformat(), code, resonance_id,
                entry_source, eligibility, normalized_value,
            ),
        }
    return decisions


def _volume_audit(module, parsed, sources, sessions, role, candidate,
                  volume_decisions=None):
    snapshots = _signal_snapshots(parsed.records)
    counts = {
        "filled_buy_count": 0,
        "eligible_filled_buy_count": 0,
        "above_one_filled_buy_count": 0,
        "invalid_filled_buy_count": 0,
    }
    for fill in parsed.fills:
        if fill.side != "BUY":
            continue
        counts["filled_buy_count"] += 1
        key = (fill.trade_date, fill.code)
        snapshot = snapshots.get(key)
        if snapshot is None or key not in sources:
            raise ValueError("%s filled buy lacks audited snapshot" % role)
        if candidate:
            decision_key = (
                fill.trade_date, fill.code, sources[key]["resonance_id"],
            )
            decision_audit = (volume_decisions or {}).get(decision_key)
            if (decision_audit is None
                    or decision_audit["record"].get("eligibility") != "ELIGIBLE"
                    or decision_audit["record"].get("_ordinal") >= fill.ordinal):
                raise ValueError(
                    "%s filled buy lacks eligible volume audit" % role
                )
        try:
            features = module._entry_snapshot_features(
                snapshot, fill.trade_date, fill.code, sessions, role,
            )
            volume_ratio = _finite(
                features.get("volume_ratio"), "%s filled buy volume_ratio" % role,
            )
        except ValueError:
            counts["invalid_filled_buy_count"] += 1
            if candidate:
                raise ValueError(
                    "%s filled buy has invalid volume_ratio" % role
                )
            continue
        if volume_ratio > EXPECTED_VOLUME_THRESHOLD:
            counts["above_one_filled_buy_count"] += 1
            if candidate:
                raise ValueError(
                    "%s filled buy violates volume_ratio threshold" % role
                )
        else:
            counts["eligible_filled_buy_count"] += 1
    return counts


def _prepare_path(module, paths, manifest, role, candidate=False):
    parsed = module.parse_joinquant_log(paths)
    initialization = module._require_identity(parsed, role)
    if candidate:
        _candidate_identity(initialization, role)
    module._validate_training_boundary(parsed, manifest, role)
    module._filled_order_transitions(parsed.records, parsed.fills, role)
    module._reconcile_portfolio_ledger(parsed.records, role)
    registrations, _ = module._relative_records(
        parsed.records, role, manifest.sessions,
    )
    sources = module._trade_sources(parsed, registrations)
    completed, open_positions = module._pair_completed_trades(parsed.fills)
    rows = module._entry_quality_rows(
        parsed.records, completed, sources, manifest.sessions, role,
    )
    volume_decisions = (
        _candidate_volume_decisions(parsed, role, manifest.sessions)
        if candidate else {}
    )
    audit = _volume_audit(
        module, parsed, sources, manifest.sessions, role, candidate,
        volume_decisions,
    )
    return {
        "parsed": parsed,
        "initialization": initialization,
        "completed": completed,
        "open_positions": open_positions,
        "rows": rows,
        "volume_audit": audit,
        "volume_decision_path": tuple(
            value["identity"]
            for _, value in sorted(volume_decisions.items())
        ),
    }


def _wilson_lower(wins, count):
    if count == 0:
        return None
    z = 1.959963984540054
    rate = float(wins) / count
    denominator = 1.0 + z * z / count
    center = (rate + z * z / (2.0 * count)) / denominator
    half = z * math.sqrt(
        rate * (1.0 - rate) / count + z * z / (4.0 * count * count)
    ) / denominator
    return center - half


def _max_drawdown(points):
    peak = None
    maximum = 0.0
    for point in points:
        peak = point.total_value if peak is None else max(
            peak, point.total_value,
        )
        maximum = max(maximum, (peak - point.total_value) / peak)
    return maximum


def _annual_returns(points):
    result = {}
    prior_value = INITIAL_CAPITAL
    for year in EVALUATION_YEARS:
        values = [
            point.total_value for point in points
            if point.closing_date.year == year
        ]
        if not values:
            continue
        result[str(year)] = values[-1] / prior_value - 1.0
        prior_value = values[-1]
    return result


def _profit_concentration(rows):
    profits = sorted(
        (row["pnl"] for row in rows if row["pnl"] > 0), reverse=True,
    )
    gross_profit = sum(profits)
    if not profits:
        return {
            "gross_profit": 0.0,
            "top_1_gross_profit_share": None,
            "top_3_gross_profit_share": None,
            "top_10_percent_gross_profit_share": None,
        }
    top_ten_count = int(math.ceil(len(rows) * 0.10))
    return {
        "gross_profit": gross_profit,
        "top_1_gross_profit_share": profits[0] / gross_profit,
        "top_3_gross_profit_share": sum(profits[:3]) / gross_profit,
        "top_10_percent_gross_profit_share": (
            sum(profits[:top_ten_count]) / gross_profit
        ),
    }


def _path_metrics(prepared):
    parsed = prepared["parsed"]
    rows = prepared["rows"]
    completed = prepared["completed"]
    open_positions = prepared["open_positions"]
    wins = sum(row["pnl"] > 0 for row in rows)
    losses = sum(row["pnl"] < 0 for row in rows)
    gross_profit = sum(row["pnl"] for row in rows if row["pnl"] > 0)
    gross_loss = -sum(row["pnl"] for row in rows if row["pnl"] < 0)
    points = parsed.portfolio_points
    if not points:
        raise ValueError("portfolio path is empty")
    return {
        "final_value": points[-1].total_value,
        "total_return": points[-1].total_value / INITIAL_CAPITAL - 1.0,
        "max_drawdown": _max_drawdown(points),
        "annual_returns": _annual_returns(points),
        "closed_count": len(completed),
        "open_count": len(open_positions),
        "entry_count": len(completed) + len(open_positions),
        "wins": wins,
        "losses": losses,
        "win_rate": float(wins) / len(completed) if completed else None,
        "wilson_95_lower": _wilson_lower(wins, len(completed)),
        "closed_pnl": sum(row["pnl"] for row in rows),
        "profit_factor": (
            gross_profit / gross_loss if gross_loss > 0 else None
        ),
        "median_trade_return": statistics.median(
            row["return_rate"] for row in rows
        ) if rows else None,
        "worst_trade_return": min(
            (row["return_rate"] for row in rows), default=None,
        ),
        "profit_concentration": _profit_concentration(rows),
        "open_positions": [fill.code for fill in open_positions],
        "volume_audit": prepared["volume_audit"],
    }


def _not_greater(candidate, baseline, field):
    candidate_value = candidate["profit_concentration"].get(field)
    baseline_value = baseline["profit_concentration"].get(field)
    return (
        candidate_value is not None
        and baseline_value is not None
        and candidate_value <= baseline_value
    )


def _annual_gate(candidate, baseline):
    candidate_years = candidate["annual_returns"]
    baseline_years = baseline["annual_returns"]
    keys = [str(year) for year in EVALUATION_YEARS]
    if any(key not in candidate_years or key not in baseline_years for key in keys):
        return False
    return (
        all(candidate_years[key] > 0 for key in keys)
        and sum(candidate_years[key] >= baseline_years[key] for key in keys) >= 2
        and all(
            candidate_years[key] >= baseline_years[key] - 0.02
            for key in keys
        )
    )


def _acceptance(baseline, candidate, path_matches):
    baseline_ordinary = baseline["ordinary"]
    baseline_double = baseline["double_friction"]
    candidate_ordinary = candidate["ordinary"]
    candidate_double = candidate["double_friction"]
    baseline_gap = (
        baseline_ordinary["total_return"] - baseline_double["total_return"]
    )
    candidate_gap = (
        candidate_ordinary["total_return"] - candidate_double["total_return"]
    )
    gates = {
        "candidate_friction_path_identity": path_matches,
        "ordinary_total_return_not_lower": (
            candidate_ordinary["total_return"]
            >= baseline_ordinary["total_return"]
        ),
        "double_total_return_not_lower": (
            candidate_double["total_return"] >= baseline_double["total_return"]
        ),
        "ordinary_win_rate_strictly_higher": (
            candidate_ordinary["win_rate"] is not None
            and baseline_ordinary["win_rate"] is not None
            and candidate_ordinary["win_rate"] > baseline_ordinary["win_rate"]
        ),
        "double_win_rate_strictly_higher": (
            candidate_double["win_rate"] is not None
            and baseline_double["win_rate"] is not None
            and candidate_double["win_rate"] > baseline_double["win_rate"]
        ),
        "ordinary_wilson_lower_not_lower": (
            candidate_ordinary["wilson_95_lower"] is not None
            and baseline_ordinary["wilson_95_lower"] is not None
            and candidate_ordinary["wilson_95_lower"]
            >= baseline_ordinary["wilson_95_lower"]
        ),
        "double_wilson_lower_not_lower": (
            candidate_double["wilson_95_lower"] is not None
            and baseline_double["wilson_95_lower"] is not None
            and candidate_double["wilson_95_lower"]
            >= baseline_double["wilson_95_lower"]
        ),
        "ordinary_drawdown_lower_and_below_fifteen_percent": (
            candidate_ordinary["max_drawdown"]
            < baseline_ordinary["max_drawdown"]
            and candidate_ordinary["max_drawdown"] < 0.15
        ),
        "double_drawdown_lower_and_below_fifteen_percent": (
            candidate_double["max_drawdown"] < baseline_double["max_drawdown"]
            and candidate_double["max_drawdown"] < 0.15
        ),
        "ordinary_closed_count_at_least_eighty_percent": (
            candidate_ordinary["closed_count"]
            >= math.ceil(baseline_ordinary["closed_count"] * 0.80)
        ),
        "double_closed_count_at_least_eighty_percent": (
            candidate_double["closed_count"]
            >= math.ceil(baseline_double["closed_count"] * 0.80)
        ),
        "ordinary_entry_count_at_least_eighty_percent": (
            candidate_ordinary["entry_count"]
            >= math.ceil(baseline_ordinary["entry_count"] * 0.80)
        ),
        "double_entry_count_at_least_eighty_percent": (
            candidate_double["entry_count"]
            >= math.ceil(baseline_double["entry_count"] * 0.80)
        ),
        "ordinary_annual_stability": _annual_gate(
            candidate_ordinary, baseline_ordinary,
        ),
        "double_annual_stability": _annual_gate(
            candidate_double, baseline_double,
        ),
        "ordinary_profit_concentration_not_higher": all(
            _not_greater(candidate_ordinary, baseline_ordinary, field)
            for field in (
                "top_1_gross_profit_share", "top_3_gross_profit_share",
                "top_10_percent_gross_profit_share",
            )
        ),
        "double_profit_concentration_not_higher": all(
            _not_greater(candidate_double, baseline_double, field)
            for field in (
                "top_1_gross_profit_share", "top_3_gross_profit_share",
                "top_10_percent_gross_profit_share",
            )
        ),
        "ordinary_open_count_not_higher": (
            candidate_ordinary["open_count"] <= baseline_ordinary["open_count"]
        ),
        "double_open_count_not_higher": (
            candidate_double["open_count"] <= baseline_double["open_count"]
        ),
        "friction_return_gap_not_higher": candidate_gap <= baseline_gap,
    }
    return {
        "gates": gates,
        "baseline_friction_return_gap": baseline_gap,
        "candidate_friction_return_gap": candidate_gap,
        "promote": all(gates.values()),
    }


def analyze_paths(baseline_ordinary_paths, baseline_double_paths,
                  candidate_ordinary_paths, candidate_double_paths, manifest):
    baseline_ordinary = _prepare_path(
        BASELINE_RISK, baseline_ordinary_paths, manifest,
        "baseline ordinary",
    )
    baseline_double = _prepare_path(
        BASELINE_RISK, baseline_double_paths, manifest,
        "baseline double friction",
    )
    candidate_ordinary = _prepare_path(
        CANDIDATE_RISK, candidate_ordinary_paths, manifest,
        "candidate ordinary", candidate=True,
    )
    candidate_double = _prepare_path(
        CANDIDATE_RISK, candidate_double_paths, manifest,
        "candidate double friction", candidate=True,
    )
    baseline_path = BASELINE_RISK._reconcile_paths(
        baseline_ordinary["parsed"], baseline_double["parsed"],
    )
    candidate_path = CANDIDATE_RISK._reconcile_paths(
        candidate_ordinary["parsed"], candidate_double["parsed"],
    )
    candidate_volume_path_match = (
        candidate_ordinary["volume_decision_path"]
        == candidate_double["volume_decision_path"]
    )
    if not candidate_volume_path_match:
        raise ValueError("candidate volume eligibility paths differ")
    baseline_metrics = {
        "ordinary": _path_metrics(baseline_ordinary),
        "double_friction": _path_metrics(baseline_double),
    }
    candidate_metrics = {
        "ordinary": _path_metrics(candidate_ordinary),
        "double_friction": _path_metrics(candidate_double),
    }
    return {
        "source_files": {
            "baseline_ordinary": _source_file_report(baseline_ordinary_paths),
            "baseline_double_friction": _source_file_report(
                baseline_double_paths,
            ),
            "candidate_ordinary": _source_file_report(candidate_ordinary_paths),
            "candidate_double_friction": _source_file_report(
                candidate_double_paths,
            ),
        },
        "session_calendar": BASELINE_RISK._manifest_report(manifest),
        "identity": {
            "baseline_build": BASELINE_BUILD,
            "candidate_build": CANDIDATE_BUILD,
            "atr_exit_policy": EXPECTED_ATR_POLICY,
            "relative_buy_policy": EXPECTED_RELATIVE_BUY_POLICY,
            "new_buy_volume_policy": EXPECTED_VOLUME_POLICY,
            "new_buy_volume_threshold": EXPECTED_VOLUME_THRESHOLD,
        },
        "path_reconciliation": {
            "baseline_friction": baseline_path,
            "candidate_friction": candidate_path,
        },
        "candidate_volume_decision_reconciliation": {
            "decision_count": len(candidate_ordinary["volume_decision_path"]),
            "identity_match": candidate_volume_path_match,
        },
        "baseline": baseline_metrics,
        "candidate": candidate_metrics,
        "acceptance": _acceptance(
            baseline_metrics, candidate_metrics,
            candidate_path["identity_match"],
        ),
    }


def _paths_alias(left, right):
    return BASELINE_RISK._paths_alias(left, right)


def _argument_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-ordinary-log", action="append", required=True)
    parser.add_argument(
        "--baseline-double-friction-log", action="append", required=True,
    )
    parser.add_argument("--candidate-ordinary-log", action="append", required=True)
    parser.add_argument(
        "--candidate-double-friction-log", action="append", required=True,
    )
    parser.add_argument("--session-calendar", required=True)
    parser.add_argument("--session-calendar-sha256", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main(argv=None):
    args = _argument_parser().parse_args(argv)
    inputs = (
        list(args.baseline_ordinary_log)
        + list(args.baseline_double_friction_log)
        + list(args.candidate_ordinary_log)
        + list(args.candidate_double_friction_log)
        + [args.session_calendar]
    )
    if any(_paths_alias(args.output, value) for value in inputs):
        raise ValueError("output aliases an input")
    for index, left in enumerate(inputs):
        for right in inputs[index + 1:]:
            if _paths_alias(left, right):
                raise ValueError("analysis inputs must be distinct")
    raw_manifest = BASELINE_RISK.read_session_calendar_manifest_bytes(
        args.session_calendar
    )
    manifest = BASELINE_RISK.validate_session_calendar_manifest(
        raw_manifest, args.session_calendar_sha256,
    )
    report = analyze_paths(
        args.baseline_ordinary_log,
        args.baseline_double_friction_log,
        args.candidate_ordinary_log,
        args.candidate_double_friction_log,
        manifest,
    )
    BASELINE_RISK._write_json_atomically(args.output, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
