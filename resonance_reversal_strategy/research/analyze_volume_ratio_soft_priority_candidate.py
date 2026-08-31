"""Fail-closed ordinary-path screen for the volume soft-priority candidate."""

import argparse
from collections import Counter
from datetime import date, datetime
import hashlib
import importlib.util
import math
import pathlib
import statistics


BASELINE_BUILD = "20260828.5"
CANDIDATE_BUILD = "20260831.2"
EXPECTED_ATR_POLICY = "OBSERVE_ONLY"
EXPECTED_RELATIVE_BUY_POLICY = "EMPTY_SLOT_BACKFILL"
EXPECTED_VOLUME_POLICY = "T1_VOLUME_RATIO_SOFT_PRIORITY_WITH_FALLBACK"
EXPECTED_VOLUME_THRESHOLD = 1.0
INITIAL_CAPITAL = 20000.0
MAX_HOLDINGS = 3
EVALUATION_YEARS = (2019, 2020, 2021)
PRIORITIES = (
    "AT_OR_BELOW_ONE",
    "ABOVE_ONE_FALLBACK",
    "INVALID_FALLBACK",
)


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
    "_resonance_soft_priority_baseline_risk", BASELINE_BUILD,
)
CANDIDATE_RISK = _load_risk_analyzer(
    "_resonance_soft_priority_candidate_risk", CANDIDATE_BUILD,
)


def _finite(value, label, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be finite" % label)
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("%s must be finite" % label)
    if nonnegative and result < 0:
        raise ValueError("%s must be nonnegative" % label)
    return result


def _source_file_report(paths):
    result = []
    for path in sorted(
            pathlib.Path(value).expanduser().resolve(strict=True)
            for value in paths):
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        result.append({"path": str(path), "sha256": digest.hexdigest()})
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


def _normalized_volume(value, label):
    if value is None:
        return None
    try:
        return _finite(value, label, nonnegative=True)
    except ValueError:
        return None


def _expected_priority(value):
    if value is None:
        return "INVALID_FALLBACK"
    if value > EXPECTED_VOLUME_THRESHOLD:
        return "ABOVE_ONE_FALLBACK"
    return "AT_OR_BELOW_ONE"


def _candidate_priority_audit(parsed, role, sessions):
    previous_session = {
        current: previous for previous, current in zip(sessions, sessions[1:])
    }
    sorted_records = {}
    for record in parsed.records:
        if record.get("event") != "resonance_decision":
            continue
        reason = record.get("reason") or ""
        if reason.startswith("BUY_CANDIDATE_SORTED:"):
            source = "FORMAL"
            prefix = "BUY_CANDIDATE_SORTED:"
        elif reason.startswith("RELATIVE_BUY_CANDIDATE_SORTED:"):
            source = "RELATIVE"
            prefix = "RELATIVE_BUY_CANDIDATE_SORTED:"
        else:
            continue
        try:
            rank = int(reason[len(prefix):])
        except ValueError as exc:
            raise ValueError("%s sorted candidate rank is invalid" % role) from exc
        timestamp = record.get("_timestamp")
        key = (
            timestamp.date() if isinstance(timestamp, datetime) else None,
            source, record.get("code"), record.get("resonance_id"),
        )
        if (rank <= 0 or key in sorted_records
                or record.get("accepted") is not True
                or record.get("direction") != "BUY_TURN"):
            raise ValueError("%s sorted candidate is invalid" % role)
        sorted_records[key] = (rank, record)

    decisions = {}
    for record in parsed.records:
        if record.get("event") != "new_buy_volume_priority":
            continue
        timestamp = record.get("_timestamp")
        code = record.get("code")
        resonance_id = record.get("resonance_id")
        source = record.get("entry_source")
        priority = record.get("priority")
        original_rank = record.get("original_rank")
        priority_rank = record.get("priority_rank")
        try:
            threshold = _finite(
                record.get("threshold"), "%s priority threshold" % role,
            )
            signal_date = date.fromisoformat(record.get("signal_date"))
        except (TypeError, ValueError) as exc:
            raise ValueError("%s priority audit is invalid" % role) from exc
        if (record.get("build") != CANDIDATE_BUILD
                or record.get("policy") != EXPECTED_VOLUME_POLICY
                or threshold != EXPECTED_VOLUME_THRESHOLD
                or not isinstance(timestamp, datetime)
                or not isinstance(code, str) or not code
                or not isinstance(resonance_id, str) or not resonance_id
                or source not in ("FORMAL", "RELATIVE")
                or priority not in PRIORITIES
                or isinstance(original_rank, bool)
                or not isinstance(original_rank, int)
                or original_rank <= 0
                or isinstance(priority_rank, bool)
                or not isinstance(priority_rank, int)
                or priority_rank <= 0
                or record.get("decision_date")
                != timestamp.date().isoformat()):
            raise ValueError("%s priority audit is invalid" % role)
        if previous_session.get(timestamp.date()) != signal_date:
            raise ValueError("%s priority signal date is not T-1" % role)
        expected_source = (
            "RELATIVE" if resonance_id.startswith("RELATIVE:") else "FORMAL"
        )
        if source != expected_source:
            raise ValueError("%s priority source mismatch" % role)
        raw_value = record.get("volume_ratio")
        normalized = _normalized_volume(
            raw_value, "%s priority volume_ratio" % role,
        )
        if priority == "INVALID_FALLBACK":
            if raw_value is not None:
                raise ValueError("%s invalid priority has a value" % role)
        elif normalized is None:
            raise ValueError("%s priority volume_ratio is invalid" % role)
        if priority != _expected_priority(normalized):
            raise ValueError("%s priority classification mismatch" % role)
        key = (timestamp.date(), source, code, resonance_id)
        if key in decisions:
            raise ValueError("%s duplicate priority audit" % role)
        sorted_match = sorted_records.get(key)
        if (sorted_match is None
                or sorted_match[0] != priority_rank
                or record.get("_ordinal") >= sorted_match[1].get("_ordinal")):
            raise ValueError("%s priority sorted decision mismatch" % role)
        decisions[key] = {
            "decision_date": timestamp.date().isoformat(),
            "entry_source": source,
            "code": code,
            "resonance_id": resonance_id,
            "signal_date": signal_date.isoformat(),
            "priority": priority,
            "volume_ratio": normalized,
            "original_rank": original_rank,
            "priority_rank": priority_rank,
        }
    if set(decisions) != set(sorted_records):
        raise ValueError("%s priority audit coverage mismatch" % role)

    grouped = {}
    for key, row in decisions.items():
        grouped.setdefault((key[0], key[1]), []).append(row)
    for rows in grouped.values():
        count = len(rows)
        if (sorted(row["original_rank"] for row in rows)
                != list(range(1, count + 1))
                or sorted(row["priority_rank"] for row in rows)
                != list(range(1, count + 1))):
            raise ValueError("%s priority ranks are not contiguous" % role)
        original = sorted(rows, key=lambda row: row["original_rank"])
        expected = (
            [row for row in original
             if row["priority"] == "AT_OR_BELOW_ONE"]
            + [row for row in original
               if row["priority"] != "AT_OR_BELOW_ONE"]
        )
        actual = sorted(rows, key=lambda row: row["priority_rank"])
        if [row["resonance_id"] for row in actual] != [
                row["resonance_id"] for row in expected]:
            raise ValueError("%s stable priority order mismatch" % role)

    source_order = {"FORMAL": 0, "RELATIVE": 1}
    ordered = sorted(
        decisions.values(),
        key=lambda row: (
            row["decision_date"], source_order[row["entry_source"]],
            row["priority_rank"],
        ),
    )
    return {
        "decision_count": len(ordered),
        "priority_counts": dict(sorted(Counter(
            row["priority"] for row in ordered
        ).items())),
        "ordered_path": ordered,
    }


def _priority_snapshot_reconciliation(parsed, audit, role):
    snapshots = {}
    for record in parsed.records:
        if record.get("event") != "signal_snapshot":
            continue
        timestamp = record.get("_timestamp")
        code = record.get("code")
        if not isinstance(timestamp, datetime) or not isinstance(code, str):
            continue
        key = (timestamp.date().isoformat(), code)
        if key in snapshots:
            raise ValueError("%s duplicate signal snapshot" % role)
        snapshots[key] = record
    for row in audit["ordered_path"]:
        snapshot = snapshots.get((row["decision_date"], row["code"]))
        if (snapshot is None or snapshot.get("valid") is not True
                or snapshot.get("build") != CANDIDATE_BUILD
                or snapshot.get("signal_date") != row["signal_date"]):
            raise ValueError("%s priority signal snapshot mismatch" % role)
        values = snapshot.get("observation_values")
        raw_value = values.get("volume_ratio") if isinstance(values, dict) else None
        normalized = _normalized_volume(
            raw_value, "%s snapshot volume_ratio" % role,
        )
        if (normalized != row["volume_ratio"]
                or _expected_priority(normalized) != row["priority"]):
            raise ValueError("%s priority snapshot value mismatch" % role)


def _filled_volume_audit(prepared, candidate):
    buy_fills = [
        fill for fill in prepared["parsed"].fills if fill.side == "BUY"
    ]
    identities = {(fill.trade_date, fill.code) for fill in buy_fills}
    snapshots = {}
    for record in prepared["parsed"].records:
        if record.get("event") != "signal_snapshot":
            continue
        timestamp = record.get("_timestamp")
        code = record.get("code")
        if not isinstance(timestamp, datetime) or not isinstance(code, str):
            continue
        key = (timestamp.date(), code)
        if key not in identities:
            continue
        if key in snapshots:
            raise ValueError("filled buy has duplicate signal snapshot")
        snapshots[key] = record
    priorities = {}
    if candidate:
        for row in prepared["priority_audit"]["ordered_path"]:
            key = (
                row["decision_date"], row["entry_source"], row["code"],
                row["resonance_id"],
            )
            priorities[key] = row
    counts = Counter()
    expected_build = CANDIDATE_BUILD if candidate else BASELINE_BUILD
    for fill in buy_fills:
        identity = (fill.trade_date, fill.code)
        source = prepared["sources"].get(identity)
        snapshot = snapshots.get(identity)
        if (source is None or snapshot is None
                or snapshot.get("valid") is not True
                or snapshot.get("build") != expected_build
                or snapshot.get("signal_date") != source.get("signal_date")):
            raise ValueError("filled buy signal snapshot mismatch")
        values = snapshot.get("observation_values")
        raw_value = values.get("volume_ratio") if isinstance(values, dict) else None
        value = _normalized_volume(raw_value, "filled buy volume_ratio")
        expected = _expected_priority(value)
        if candidate:
            key = (
                fill.trade_date.isoformat(), source["entry_source"], fill.code,
                source["resonance_id"],
            )
            priority = priorities.get(key)
            if (priority is None or priority["priority"] != expected
                    or priority["volume_ratio"] != value):
                raise ValueError("candidate filled buy priority mismatch")
        counts[expected] += 1
    return {
        "filled_buy_count": len(buy_fills),
        "at_or_below_one_filled_buy_count": counts["AT_OR_BELOW_ONE"],
        "above_one_filled_buy_count": counts["ABOVE_ONE_FALLBACK"],
        "invalid_filled_buy_count": counts["INVALID_FALLBACK"],
    }


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
    priority_audit = (
        _candidate_priority_audit(parsed, role, manifest.sessions)
        if candidate else None
    )
    if candidate:
        _priority_snapshot_reconciliation(parsed, priority_audit, role)
    prepared = {
        "parsed": parsed,
        "initialization": initialization,
        "completed": completed,
        "open_positions": open_positions,
        "rows": rows,
        "sources": sources,
        "priority_audit": priority_audit,
    }
    prepared["volume_audit"] = _filled_volume_audit(prepared, candidate)
    return prepared


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
    points = parsed.portfolio_points
    if not points:
        raise ValueError("portfolio path is empty")
    wins = sum(row["pnl"] > 0 for row in rows)
    losses = sum(row["pnl"] < 0 for row in rows)
    gross_profit = sum(row["pnl"] for row in rows if row["pnl"] > 0)
    gross_loss = -sum(row["pnl"] for row in rows if row["pnl"] < 0)
    cash_ratios = [point.available_cash / point.total_value for point in points]
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
        "mean_cash_ratio": statistics.fmean(cash_ratios),
        "sessions_below_max_holdings": sum(
            len(point.positions) < MAX_HOLDINGS for point in points
        ),
        "open_positions": [fill.code for fill in open_positions],
        "volume_audit": prepared["volume_audit"],
        "priority_audit": prepared["priority_audit"],
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


def _ordinary_acceptance(baseline, candidate):
    gates = {
        "total_return_not_lower": (
            candidate["total_return"] >= baseline["total_return"]
        ),
        "win_rate_strictly_higher": (
            candidate["win_rate"] is not None
            and baseline["win_rate"] is not None
            and candidate["win_rate"] > baseline["win_rate"]
        ),
        "wilson_lower_not_lower": (
            candidate["wilson_95_lower"] is not None
            and baseline["wilson_95_lower"] is not None
            and candidate["wilson_95_lower"] >= baseline["wilson_95_lower"]
        ),
        "drawdown_lower_and_below_fifteen_percent": (
            candidate["max_drawdown"] < baseline["max_drawdown"]
            and candidate["max_drawdown"] < 0.15
        ),
        "closed_count_at_least_eighty_percent": (
            candidate["closed_count"]
            >= math.ceil(baseline["closed_count"] * 0.80)
        ),
        "entry_count_at_least_eighty_percent": (
            candidate["entry_count"]
            >= math.ceil(baseline["entry_count"] * 0.80)
        ),
        "annual_stability": _annual_gate(candidate, baseline),
        "profit_concentration_not_higher": all(
            _not_greater(candidate, baseline, field)
            for field in (
                "top_1_gross_profit_share",
                "top_3_gross_profit_share",
                "top_10_percent_gross_profit_share",
            )
        ),
        "open_count_not_higher": (
            candidate["open_count"] <= baseline["open_count"]
        ),
        "worst_trade_not_worse": (
            candidate["worst_trade_return"]
            >= baseline["worst_trade_return"]
        ),
        "mean_cash_ratio_not_higher": (
            candidate["mean_cash_ratio"] <= baseline["mean_cash_ratio"]
        ),
        "underfilled_sessions_not_higher": (
            candidate["sessions_below_max_holdings"]
            <= baseline["sessions_below_max_holdings"]
        ),
        "no_invalid_filled_buys": (
            candidate["volume_audit"]["invalid_filled_buy_count"] == 0
        ),
    }
    return {
        "gates": gates,
        "promote_to_double_friction": all(gates.values()),
    }


def analyze_paths(baseline_paths, candidate_paths, manifest):
    baseline = _prepare_path(
        BASELINE_RISK, baseline_paths, manifest, "baseline ordinary",
    )
    candidate = _prepare_path(
        CANDIDATE_RISK, candidate_paths, manifest,
        "candidate ordinary", candidate=True,
    )
    baseline_metrics = _path_metrics(baseline)
    candidate_metrics = _path_metrics(candidate)
    return {
        "scope": {
            "processing_stage": "POST_BACKTEST_REAL_PATH_COMPARISON",
            "friction_stage": "ORDINARY_ONLY_PRE_SCREEN",
            "threshold_search_performed": False,
            "validation_period_used": False,
            "double_friction_run_required_now": False,
        },
        "source_files": {
            "baseline_ordinary": _source_file_report(baseline_paths),
            "candidate_ordinary": _source_file_report(candidate_paths),
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
        "baseline": baseline_metrics,
        "candidate": candidate_metrics,
        "acceptance": _ordinary_acceptance(
            baseline_metrics, candidate_metrics,
        ),
    }


def _paths_alias(left, right):
    return BASELINE_RISK._paths_alias(left, right)


def _argument_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-ordinary-log", action="append", required=True)
    parser.add_argument("--candidate-ordinary-log", action="append", required=True)
    parser.add_argument("--session-calendar", required=True)
    parser.add_argument("--session-calendar-sha256", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main(argv=None):
    args = _argument_parser().parse_args(argv)
    inputs = (
        list(args.baseline_ordinary_log)
        + list(args.candidate_ordinary_log)
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
        args.baseline_ordinary_log, args.candidate_ordinary_log, manifest,
    )
    BASELINE_RISK._write_json_atomically(args.output, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
