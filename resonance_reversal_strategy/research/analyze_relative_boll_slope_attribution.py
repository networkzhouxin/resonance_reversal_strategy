"""Read-only T-1 BOLL mid-slope attribution for filled RELATIVE buys."""

import argparse
import importlib.util
import math
import pathlib
import statistics


BASELINE_BUILD = "20260828.5"
COMPARISON_BUILD = "20260831.2"
SLOPE_NONNEGATIVE = "SLOPE_NONNEGATIVE"
SLOPE_NEGATIVE = "SLOPE_NEGATIVE"
PRIMARY_METRICS = ("win_rate", "pnl_per_trade", "median_return")


def _load_volume_analyzer():
    path = pathlib.Path(__file__).with_name(
        "analyze_volume_ratio_soft_priority_candidate.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_resonance_relative_slope_volume_analyzer", path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VOLUME_ANALYZER = _load_volume_analyzer()


def _finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be finite" % label)
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("%s must be finite" % label)
    return result


def _safe_rate(numerator, denominator):
    return float(numerator) / denominator if denominator else None


def _basic_summary(rows):
    wins = sum(row["pnl"] > 0 for row in rows)
    losses = sum(row["pnl"] < 0 for row in rows)
    returns = [row["return_rate"] for row in rows]
    return {
        "count": len(rows),
        "wins": wins,
        "losses": losses,
        "win_rate": _safe_rate(wins, len(rows)),
        "pnl": sum(row["pnl"] for row in rows),
        "median_return": statistics.median(returns) if returns else None,
    }


def _year_summary(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["entry_date"][:4], []).append(row)
    return {
        year: _basic_summary(values)
        for year, values in sorted(grouped.items())
    }


def _excluding_largest_absolute_pnl(rows):
    if not rows:
        return None
    excluded = max(rows, key=lambda row: abs(row["pnl"]))
    remaining = [row for row in rows if row is not excluded]
    summary = _basic_summary(remaining)
    return {
        "excluded_code": excluded["code"],
        "excluded_entry_date": excluded["entry_date"],
        **summary,
    }


def _cohort_summary(rows):
    summary = _basic_summary(rows)
    gross_profit = sum(row["pnl"] for row in rows if row["pnl"] > 0)
    gross_loss = -sum(row["pnl"] for row in rows if row["pnl"] < 0)
    summary.update({
        "breakeven": sum(row["pnl"] == 0 for row in rows),
        "wilson_95_lower": VOLUME_ANALYZER._wilson_lower(
            summary["wins"], summary["count"],
        ),
        "pnl_per_trade": _safe_rate(summary["pnl"], summary["count"]),
        "profit_factor": (
            gross_profit / gross_loss if gross_loss > 0 else None
        ),
        "worst_trade_return": min(
            (row["return_rate"] for row in rows), default=None,
        ),
        "profit_concentration": VOLUME_ANALYZER._profit_concentration(rows),
        "by_entry_year": _year_summary(rows),
        "excluding_largest_absolute_pnl": (
            _excluding_largest_absolute_pnl(rows)
        ),
    })
    return summary


def _metric_delta(nonnegative, negative, metric):
    left = nonnegative.get(metric)
    right = negative.get(metric)
    if left is None or right is None:
        return None
    return left - right


def summarize_relative_slope(rows):
    relative_rows = []
    excluded = 0
    groups = {SLOPE_NONNEGATIVE: [], SLOPE_NEGATIVE: []}
    for row in rows:
        if row.get("entry_source") != "RELATIVE":
            excluded += 1
            continue
        features = row.get("features")
        if not isinstance(features, dict):
            raise ValueError("normalized_boll_mid_slope is missing")
        slope = _finite(
            features.get("normalized_boll_mid_slope"),
            "normalized_boll_mid_slope",
        )
        group = SLOPE_NONNEGATIVE if slope >= 0 else SLOPE_NEGATIVE
        groups[group].append(row)
        relative_rows.append(row)
    if not relative_rows:
        raise ValueError("no completed RELATIVE entries are available")
    summaries = {
        name: _cohort_summary(values) for name, values in groups.items()
    }
    deltas = {
        metric: _metric_delta(
            summaries[SLOPE_NONNEGATIVE], summaries[SLOPE_NEGATIVE], metric,
        )
        for metric in PRIMARY_METRICS
    }
    return {
        "included_relative_closed_count": len(relative_rows),
        "excluded_non_relative_closed_count": excluded,
        "boundary": {
            "nonnegative": ">= 0",
            "negative": "< 0",
            "threshold_search_performed": False,
        },
        "groups": summaries,
        "comparison": {"nonnegative_minus_negative": deltas},
    }


def _direction(value):
    if value is None:
        return None
    if value > 0:
        return "POSITIVE"
    if value < 0:
        return "NEGATIVE"
    return "ZERO"


def directional_replication(baseline, comparison):
    baseline_delta = baseline["comparison"]["nonnegative_minus_negative"]
    comparison_delta = comparison["comparison"]["nonnegative_minus_negative"]
    same_direction = {
        metric: (
            _direction(baseline_delta.get(metric)) is not None
            and _direction(baseline_delta.get(metric))
            == _direction(comparison_delta.get(metric))
        )
        for metric in PRIMARY_METRICS
    }
    positive_in_both = {
        metric: (
            _direction(baseline_delta.get(metric)) == "POSITIVE"
            and _direction(comparison_delta.get(metric)) == "POSITIVE"
        )
        for metric in PRIMARY_METRICS
    }
    return {
        "baseline_delta": baseline_delta,
        "comparison_delta": comparison_delta,
        "same_direction": same_direction,
        "positive_in_both_versions": positive_in_both,
        "all_primary_metrics_same_direction": all(same_direction.values()),
        "all_primary_metrics_positive_in_both_versions": all(
            positive_in_both.values()
        ),
        "rule_candidate_created": False,
    }


def _open_position_scope(prepared):
    counts = {"RELATIVE": 0, "FORMAL": 0}
    codes = []
    for fill in prepared["open_positions"]:
        source = prepared["sources"][(fill.trade_date, fill.code)][
            "entry_source"
        ]
        counts[source] = counts.get(source, 0) + 1
        codes.append({
            "code": fill.code,
            "entry_date": fill.trade_date.isoformat(),
            "entry_source": source,
        })
    return {
        "excluded_from_attribution": True,
        "count": len(codes),
        "by_entry_source": counts,
        "positions": codes,
    }


def analyze_paths(baseline_paths, comparison_paths, manifest):
    baseline_prepared = VOLUME_ANALYZER._prepare_path(
        VOLUME_ANALYZER.BASELINE_RISK,
        baseline_paths,
        manifest,
        "baseline ordinary",
    )
    comparison_prepared = VOLUME_ANALYZER._prepare_path(
        VOLUME_ANALYZER.CANDIDATE_RISK,
        comparison_paths,
        manifest,
        "comparison ordinary",
        candidate=True,
    )
    baseline = summarize_relative_slope(baseline_prepared["rows"])
    comparison = summarize_relative_slope(comparison_prepared["rows"])
    return {
        "scope": {
            "processing_stage": (
                "POST_BACKTEST_READ_ONLY_RELATIVE_ENTRY_TREND_ATTRIBUTION"
            ),
            "path_assumption": "ORIGINAL_TRADE_PATH_FIXED",
            "entry_source": "RELATIVE_ONLY",
            "friction_profile": "ORDINARY_ONLY",
            "strategy_behavior_changed": False,
            "validation_period_used": False,
            "threshold_search_performed": False,
            "rule_candidate_created": False,
        },
        "source_files": {
            "baseline_ordinary": VOLUME_ANALYZER._source_file_report(
                baseline_paths
            ),
            "comparison_ordinary": VOLUME_ANALYZER._source_file_report(
                comparison_paths
            ),
        },
        "session_calendar": VOLUME_ANALYZER.BASELINE_RISK._manifest_report(
            manifest
        ),
        "identity": {
            "baseline_build": BASELINE_BUILD,
            "comparison_build": COMPARISON_BUILD,
            "atr_exit_policy": VOLUME_ANALYZER.EXPECTED_ATR_POLICY,
            "relative_buy_policy": (
                VOLUME_ANALYZER.EXPECTED_RELATIVE_BUY_POLICY
            ),
            "comparison_volume_policy": (
                VOLUME_ANALYZER.EXPECTED_VOLUME_POLICY
            ),
            "comparison_volume_threshold": (
                VOLUME_ANALYZER.EXPECTED_VOLUME_THRESHOLD
            ),
        },
        "baseline": baseline,
        "comparison": comparison,
        "directional_replication": directional_replication(
            baseline, comparison,
        ),
        "terminal_open_positions": {
            "baseline": _open_position_scope(baseline_prepared),
            "comparison": _open_position_scope(comparison_prepared),
        },
    }


def _paths_alias(left, right):
    return VOLUME_ANALYZER._paths_alias(left, right)


def _argument_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-ordinary-log", action="append", required=True)
    parser.add_argument("--comparison-ordinary-log", action="append", required=True)
    parser.add_argument("--session-calendar", required=True)
    parser.add_argument("--session-calendar-sha256", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main(argv=None):
    args = _argument_parser().parse_args(argv)
    inputs = (
        list(args.baseline_ordinary_log)
        + list(args.comparison_ordinary_log)
        + [args.session_calendar]
    )
    if any(_paths_alias(args.output, value) for value in inputs):
        raise ValueError("output aliases an input")
    for index, left in enumerate(inputs):
        for right in inputs[index + 1:]:
            if _paths_alias(left, right):
                raise ValueError("analysis inputs must be distinct")
    raw_manifest = (
        VOLUME_ANALYZER.BASELINE_RISK.read_session_calendar_manifest_bytes(
            args.session_calendar
        )
    )
    manifest = VOLUME_ANALYZER.BASELINE_RISK.validate_session_calendar_manifest(
        raw_manifest, args.session_calendar_sha256,
    )
    report = analyze_paths(
        args.baseline_ordinary_log, args.comparison_ordinary_log, manifest,
    )
    VOLUME_ANALYZER.BASELINE_RISK._write_json_atomically(args.output, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
