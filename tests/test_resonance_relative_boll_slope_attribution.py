import importlib.util
from pathlib import Path

import pytest


ANALYZER_PATH = (
    Path(__file__).resolve().parents[1]
    / "resonance_reversal_strategy"
    / "research"
    / "analyze_relative_boll_slope_attribution.py"
)


def load_analyzer():
    spec = importlib.util.spec_from_file_location(
        "resonance_relative_boll_slope_attribution", ANALYZER_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row(source, year, slope, pnl, return_rate):
    return {
        "code": "TEST.XSHG",
        "entry_date": "%d-01-02" % year,
        "entry_source": source,
        "entry_branch": "SOFT_ALL_THREE" if source == "RELATIVE" else "FORMAL",
        "supporters": "BOLL+KDJ+RSI",
        "entry_rank": 1,
        "pnl": pnl,
        "return_rate": return_rate,
        "features": {"normalized_boll_mid_slope": slope},
    }


def test_relative_slope_attribution_uses_zero_as_nonnegative_boundary():
    analyzer = load_analyzer()
    rows = [
        row("RELATIVE", 2019, 0.0, 100.0, 0.10),
        row("RELATIVE", 2020, 0.01, -20.0, -0.02),
        row("RELATIVE", 2021, -0.01, 30.0, 0.03),
        row("FORMAL", 2021, -0.02, -500.0, -0.50),
    ]

    result = analyzer.summarize_relative_slope(rows)

    assert result["included_relative_closed_count"] == 3
    assert result["excluded_non_relative_closed_count"] == 1
    assert result["groups"]["SLOPE_NONNEGATIVE"]["count"] == 2
    assert result["groups"]["SLOPE_NONNEGATIVE"]["wins"] == 1
    assert result["groups"]["SLOPE_NONNEGATIVE"]["pnl"] == pytest.approx(80.0)
    assert result["groups"]["SLOPE_NEGATIVE"]["count"] == 1
    assert result["groups"]["SLOPE_NEGATIVE"]["pnl"] == pytest.approx(30.0)
    assert result["comparison"]["nonnegative_minus_negative"]["win_rate"] == pytest.approx(-0.5)


def test_relative_slope_attribution_reports_years_concentration_and_outlier_check():
    analyzer = load_analyzer()
    rows = [
        row("RELATIVE", 2019, 0.01, 100.0, 0.10),
        row("RELATIVE", 2019, 0.02, 40.0, 0.04),
        row("RELATIVE", 2020, 0.03, -10.0, -0.01),
        row("RELATIVE", 2021, -0.01, 30.0, 0.03),
        row("RELATIVE", 2021, -0.02, -20.0, -0.02),
    ]

    result = analyzer.summarize_relative_slope(rows)
    nonnegative = result["groups"]["SLOPE_NONNEGATIVE"]

    assert nonnegative["by_entry_year"]["2019"] == {
        "count": 2,
        "wins": 2,
        "losses": 0,
        "win_rate": 1.0,
        "pnl": 140.0,
        "median_return": 0.07,
    }
    assert nonnegative["profit_concentration"]["top_1_gross_profit_share"] == pytest.approx(100.0 / 140.0)
    assert nonnegative["profit_concentration"]["top_3_gross_profit_share"] == pytest.approx(1.0)
    assert nonnegative["profit_concentration"]["top_10_percent_gross_profit_share"] == pytest.approx(100.0 / 140.0)
    assert nonnegative["excluding_largest_absolute_pnl"] == {
        "excluded_code": "TEST.XSHG",
        "excluded_entry_date": "2019-01-02",
        "count": 2,
        "wins": 1,
        "losses": 1,
        "win_rate": 0.5,
        "pnl": 30.0,
        "median_return": 0.015,
    }


def test_relative_slope_attribution_fails_closed_on_missing_or_invalid_slope():
    analyzer = load_analyzer()
    missing = row("RELATIVE", 2019, 0.1, 10.0, 0.01)
    del missing["features"]["normalized_boll_mid_slope"]

    with pytest.raises(ValueError, match="normalized_boll_mid_slope"):
        analyzer.summarize_relative_slope([missing])
    with pytest.raises(ValueError, match="normalized_boll_mid_slope"):
        analyzer.summarize_relative_slope([
            row("RELATIVE", 2019, float("nan"), 10.0, 0.01),
        ])


def test_directional_replication_does_not_create_a_rule_candidate():
    analyzer = load_analyzer()
    baseline = analyzer.summarize_relative_slope([
        row("RELATIVE", 2019, 0.01, 20.0, 0.02),
        row("RELATIVE", 2019, -0.01, -10.0, -0.01),
    ])
    comparison = analyzer.summarize_relative_slope([
        row("RELATIVE", 2019, 0.02, 30.0, 0.03),
        row("RELATIVE", 2019, -0.02, -20.0, -0.02),
    ])

    result = analyzer.directional_replication(baseline, comparison)

    assert result["same_direction"] == {
        "win_rate": True,
        "pnl_per_trade": True,
        "median_return": True,
    }
    assert result["all_primary_metrics_same_direction"] is True
    assert result["rule_candidate_created"] is False
