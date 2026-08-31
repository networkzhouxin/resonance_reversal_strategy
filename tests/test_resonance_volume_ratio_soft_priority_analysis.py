from datetime import date, datetime
import importlib.util
from pathlib import Path
import types

import pytest


ANALYZER_PATH = (
    Path(__file__).resolve().parents[1]
    / "resonance_reversal_strategy"
    / "research"
    / "analyze_volume_ratio_soft_priority_candidate.py"
)


def load_analyzer():
    spec = importlib.util.spec_from_file_location(
        "_resonance_volume_soft_priority_analysis", ANALYZER_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def priority_record(code, source, resonance_id, priority, volume_ratio,
                    original_rank, priority_rank):
    return {
        "event": "new_buy_volume_priority",
        "build": "20260831.2",
        "code": code,
        "decision_date": "2021-01-06",
        "signal_date": "2021-01-05",
        "resonance_id": resonance_id,
        "entry_source": source,
        "policy": "T1_VOLUME_RATIO_SOFT_PRIORITY_WITH_FALLBACK",
        "threshold": 1.0,
        "volume_ratio": volume_ratio,
        "priority": priority,
        "original_rank": original_rank,
        "priority_rank": priority_rank,
        "_timestamp": datetime(2021, 1, 6, 9, 35),
        "_ordinal": priority_rank * 2 - 1,
    }


def sorted_record(audit):
    prefix = (
        "RELATIVE_BUY_CANDIDATE_SORTED"
        if audit["entry_source"] == "RELATIVE"
        else "BUY_CANDIDATE_SORTED"
    )
    return {
        "event": "resonance_decision",
        "accepted": True,
        "direction": "BUY_TURN",
        "code": audit["code"],
        "resonance_id": audit["resonance_id"],
        "signal_date": audit["signal_date"],
        "reason": "%s:%s" % (prefix, audit["priority_rank"]),
        "_timestamp": audit["_timestamp"],
        "_ordinal": audit["_ordinal"] + 1,
    }


def test_priority_audit_reconciles_stable_groupwise_order_and_t_minus_one():
    analyzer = load_analyzer()
    audits = [
        priority_record(
            "510300.XSHG", "FORMAL", "formal-low",
            "AT_OR_BELOW_ONE", 0.8, 2, 1,
        ),
        priority_record(
            "159915.XSHE", "FORMAL", "formal-high",
            "ABOVE_ONE_FALLBACK", 1.2, 1, 2,
        ),
        priority_record(
            "512100.XSHG", "FORMAL", "formal-invalid",
            "INVALID_FALLBACK", None, 3, 3,
        ),
        priority_record(
            "513100.XSHG", "RELATIVE", "RELATIVE:low",
            "AT_OR_BELOW_ONE", 0.7, 1, 1,
        ),
    ]
    records = []
    for audit in audits:
        records.extend((audit, sorted_record(audit)))

    result = analyzer._candidate_priority_audit(
        types.SimpleNamespace(records=tuple(records)),
        "candidate ordinary",
        (date(2021, 1, 5), date(2021, 1, 6)),
    )

    assert result["decision_count"] == 4
    assert result["priority_counts"] == {
        "ABOVE_ONE_FALLBACK": 1,
        "AT_OR_BELOW_ONE": 2,
        "INVALID_FALLBACK": 1,
    }
    assert [row["code"] for row in result["ordered_path"]] == [
        "510300.XSHG", "159915.XSHE", "512100.XSHG", "513100.XSHG",
    ]


def test_priority_audit_rejects_nonstable_group_order():
    analyzer = load_analyzer()
    audits = [
        priority_record(
            "159915.XSHE", "FORMAL", "formal-high",
            "ABOVE_ONE_FALLBACK", 1.2, 1, 1,
        ),
        priority_record(
            "510300.XSHG", "FORMAL", "formal-low",
            "AT_OR_BELOW_ONE", 0.8, 2, 2,
        ),
    ]
    records = []
    for audit in audits:
        records.extend((audit, sorted_record(audit)))

    with pytest.raises(ValueError, match="stable priority order"):
        analyzer._candidate_priority_audit(
            types.SimpleNamespace(records=tuple(records)),
            "candidate ordinary",
            (date(2021, 1, 5), date(2021, 1, 6)),
        )


def test_priority_audit_rejects_non_t_minus_one_signal_date():
    analyzer = load_analyzer()
    audit = priority_record(
        "510300.XSHG", "FORMAL", "formal-low",
        "AT_OR_BELOW_ONE", 0.8, 1, 1,
    )
    audit["signal_date"] = "2021-01-04"

    with pytest.raises(ValueError, match="not T-1"):
        analyzer._candidate_priority_audit(
            types.SimpleNamespace(records=(audit, sorted_record(audit))),
            "candidate ordinary",
            (date(2021, 1, 5), date(2021, 1, 6)),
        )


def test_filled_volume_audit_includes_terminal_open_buy():
    analyzer = load_analyzer()
    code = "510300.XSHG"
    trade_date = date(2021, 12, 30)
    resonance_id = "formal-open"
    fill = analyzer.BASELINE_RISK.Fill(
        timestamp=datetime(2021, 12, 30, 9, 35),
        code=code,
        side="BUY",
        price=4.0,
        amount=100,
        commission=5.0,
        source_path="candidate.log",
        ordinal=10,
    )
    prepared = {
        "parsed": types.SimpleNamespace(
            fills=(fill,),
            records=({
                "event": "signal_snapshot",
                "build": "20260831.2",
                "valid": True,
                "code": code,
                "signal_date": "2021-12-29",
                "observation_values": {"volume_ratio": 0.8},
                "_timestamp": datetime(2021, 12, 30, 9, 35),
            },),
        ),
        "sources": {
            (trade_date, code): {
                "entry_source": "FORMAL",
                "resonance_id": resonance_id,
                "signal_date": "2021-12-29",
            },
        },
        "priority_audit": {
            "ordered_path": ({
                "decision_date": trade_date.isoformat(),
                "entry_source": "FORMAL",
                "code": code,
                "resonance_id": resonance_id,
                "priority": "AT_OR_BELOW_ONE",
                "volume_ratio": 0.8,
            },),
        },
    }

    result = analyzer._filled_volume_audit(prepared, candidate=True)

    assert result["filled_buy_count"] == 1
    assert result["at_or_below_one_filled_buy_count"] == 1


def baseline_metrics():
    return {
        "total_return": 0.66,
        "win_rate": 0.75,
        "wilson_95_lower": 0.64,
        "max_drawdown": 0.159,
        "closed_count": 66,
        "entry_count": 69,
        "annual_returns": {"2019": 0.24, "2020": 0.20, "2021": 0.10},
        "profit_concentration": {
            "top_1_gross_profit_share": 0.10,
            "top_3_gross_profit_share": 0.22,
            "top_10_percent_gross_profit_share": 0.38,
        },
        "open_count": 3,
        "worst_trade_return": -0.14,
        "mean_cash_ratio": 0.22,
        "sessions_below_max_holdings": 204,
        "volume_audit": {"invalid_filled_buy_count": 0},
    }


def passing_candidate_metrics():
    return {
        "total_return": 0.67,
        "win_rate": 0.77,
        "wilson_95_lower": 0.65,
        "max_drawdown": 0.149,
        "closed_count": 60,
        "entry_count": 63,
        "annual_returns": {"2019": 0.25, "2020": 0.21, "2021": 0.11},
        "profit_concentration": {
            "top_1_gross_profit_share": 0.09,
            "top_3_gross_profit_share": 0.21,
            "top_10_percent_gross_profit_share": 0.37,
        },
        "open_count": 3,
        "worst_trade_return": -0.13,
        "mean_cash_ratio": 0.20,
        "sessions_below_max_holdings": 190,
        "volume_audit": {"invalid_filled_buy_count": 0},
    }


def test_ordinary_acceptance_requires_every_preregistered_gate():
    analyzer = load_analyzer()

    result = analyzer._ordinary_acceptance(
        baseline_metrics(), passing_candidate_metrics(),
    )

    assert all(result["gates"].values())
    assert result["promote_to_double_friction"] is True


def test_ordinary_acceptance_rejects_lower_return_even_with_higher_win_rate():
    analyzer = load_analyzer()
    candidate = passing_candidate_metrics()
    candidate["total_return"] = 0.65

    result = analyzer._ordinary_acceptance(baseline_metrics(), candidate)

    assert result["gates"]["total_return_not_lower"] is False
    assert result["gates"]["win_rate_strictly_higher"] is True
    assert result["promote_to_double_friction"] is False
