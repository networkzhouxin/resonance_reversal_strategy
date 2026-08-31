import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).parents[1]
ANALYZER_PATH = (
    ROOT / "resonance_reversal_strategy" / "research"
    / "analyze_volume_ratio_candidate.py"
)
RISK_TEST_PATH = ROOT / "tests" / "test_resonance_trade_risk_analysis.py"


def _load_risk_fixtures():
    spec = importlib.util.spec_from_file_location(
        "resonance_risk_test_fixtures", RISK_TEST_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _candidate_lines(lines, volume_ratio=0.9,
                     policy="T1_VOLUME_RATIO_AT_OR_BELOW_ONE",
                     threshold=1.0, audit_signal_date=None):
    result = []
    for line in lines:
        payload_start = line.find("{")
        if payload_start < 0:
            result.append(line)
            continue
        payload = json.loads(line[payload_start:])
        if "build" in payload:
            payload["build"] = "20260831.1"
        if payload.get("event") == "strategy_initialized":
            payload["new_buy_volume_policy"] = policy
            payload["new_buy_volume_threshold"] = threshold
        if payload.get("event") == "signal_snapshot":
            payload["observation_values"]["volume_ratio"] = volume_ratio
        rewritten = (
            line[:payload_start]
            + json.dumps(payload, ensure_ascii=False, sort_keys=True)
        )
        result.append(rewritten)
        reason = payload.get("reason") or ""
        if (payload.get("event") == "resonance_decision"
                and reason in (
                    "BUY_CANDIDATE_SORTED:1",
                    "RELATIVE_BUY_CANDIDATE_SORTED:1",
                )):
            eligibility = (
                "ELIGIBLE" if 0 <= volume_ratio <= 1.0 else "ABOVE_ONE"
            )
            audit = {
                "event": "new_buy_volume_eligibility",
                "build": "20260831.1",
                "code": payload["code"],
                "decision_date": rewritten[:10],
                "signal_date": audit_signal_date or payload["signal_date"],
                "resonance_id": payload["resonance_id"],
                "entry_source": (
                    "RELATIVE"
                    if payload["resonance_id"].startswith("RELATIVE:")
                    else "FORMAL"
                ),
                "policy": policy,
                "threshold": threshold,
                "volume_ratio": volume_ratio,
                "eligibility": eligibility,
            }
            result.append(
                rewritten[:rewritten.find("{")]
                + json.dumps(audit, ensure_ascii=False, sort_keys=True)
            )
            if eligibility == "ABOVE_ONE":
                rejection = dict(payload)
                rejection["accepted"] = False
                rejection["reason"] = "BUY_VOLUME_RATIO_ABOVE_ONE"
                result.append(
                    rewritten[:rewritten.find("{")]
                    + json.dumps(
                        rejection, ensure_ascii=False, sort_keys=True,
                    )
                )
    return result


def _write_lines(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_candidate_cli(tmp_path, candidate_volume_ratio=0.9,
                       candidate_policy="T1_VOLUME_RATIO_AT_OR_BELOW_ONE",
                       candidate_double_volume_ratio=None,
                       candidate_threshold=1.0,
                       candidate_audit_signal_date=None):
    fixtures = _load_risk_fixtures()
    baseline_ordinary = tmp_path / "baseline-ordinary.log"
    baseline_double = tmp_path / "baseline-double.log"
    candidate_ordinary = tmp_path / "candidate-ordinary.log"
    candidate_double = tmp_path / "candidate-double.log"
    manifest_path = tmp_path / "sessions.json"
    output_path = tmp_path / "report.json"
    _write_lines(baseline_ordinary, fixtures._ordinary_lines())
    _write_lines(baseline_double, fixtures._double_lines())
    _write_lines(candidate_ordinary, _candidate_lines(
        fixtures._ordinary_lines(), candidate_volume_ratio, candidate_policy,
        candidate_threshold, candidate_audit_signal_date,
    ))
    double_volume_ratio = (
        candidate_volume_ratio
        if candidate_double_volume_ratio is None
        else candidate_double_volume_ratio
    )
    _write_lines(candidate_double, _candidate_lines(
        fixtures._double_lines(), double_volume_ratio, candidate_policy,
        candidate_threshold, candidate_audit_signal_date,
    ))
    raw_manifest = fixtures._manifest_bytes(fixtures.FIXTURE_SESSIONS)
    manifest_path.write_bytes(raw_manifest)
    command = [
        sys.executable, str(ANALYZER_PATH),
        "--baseline-ordinary-log", str(baseline_ordinary),
        "--baseline-double-friction-log", str(baseline_double),
        "--candidate-ordinary-log", str(candidate_ordinary),
        "--candidate-double-friction-log", str(candidate_double),
        "--session-calendar", str(manifest_path),
        "--session-calendar-sha256", hashlib.sha256(raw_manifest).hexdigest(),
        "--output", str(output_path),
    ]
    completed = subprocess.run(
        command, capture_output=True, text=True, check=False,
    )
    return completed, output_path


def test_candidate_cli_reports_real_path_metrics_and_volume_audit(tmp_path):
    completed, output_path = _run_candidate_cli(tmp_path)

    assert completed.returncode == 0, completed.stderr
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["identity"] == {
        "baseline_build": "20260828.5",
        "candidate_build": "20260831.1",
        "atr_exit_policy": "OBSERVE_ONLY",
        "relative_buy_policy": "EMPTY_SLOT_BACKFILL",
        "new_buy_volume_policy": "T1_VOLUME_RATIO_AT_OR_BELOW_ONE",
        "new_buy_volume_threshold": 1.0,
    }
    assert report["path_reconciliation"] == {
        "baseline_friction": {
            "fill_count": 2,
            "identity_match": True,
            "amount_difference_count": 2,
        },
        "candidate_friction": {
            "fill_count": 2,
            "identity_match": True,
            "amount_difference_count": 2,
        },
    }
    assert report["candidate"]["ordinary"]["closed_count"] == 1
    assert report["candidate"]["ordinary"]["open_count"] == 0
    assert report["candidate"]["ordinary"]["entry_count"] == 1
    assert report["candidate"]["ordinary"]["win_rate"] == 1.0
    assert report["candidate"]["ordinary"]["volume_audit"] == {
        "filled_buy_count": 1,
        "eligible_filled_buy_count": 1,
        "above_one_filled_buy_count": 0,
        "invalid_filled_buy_count": 0,
    }
    assert report["candidate_volume_decision_reconciliation"] == {
        "decision_count": 1,
        "identity_match": True,
    }
    assert report["acceptance"]["promote"] is False


def test_candidate_cli_rejects_filled_buy_above_threshold(tmp_path):
    completed, output_path = _run_candidate_cli(
        tmp_path, candidate_volume_ratio=1.1,
    )

    assert completed.returncode != 0
    assert not output_path.exists()
    assert "filled buy lacks eligible volume audit" in completed.stderr


def test_candidate_cli_rejects_wrong_policy_identity(tmp_path):
    completed, output_path = _run_candidate_cli(
        tmp_path, candidate_policy="UNAPPROVED_POLICY",
    )

    assert completed.returncode != 0
    assert not output_path.exists()
    assert "new_buy_volume_policy mismatch" in completed.stderr


def test_candidate_cli_rejects_friction_volume_decision_path_drift(tmp_path):
    completed, output_path = _run_candidate_cli(
        tmp_path, candidate_volume_ratio=0.9,
        candidate_double_volume_ratio=0.8,
    )

    assert completed.returncode != 0
    assert not output_path.exists()
    assert "candidate volume eligibility paths differ" in completed.stderr


def test_candidate_cli_rejects_boolean_threshold_identity(tmp_path):
    completed, output_path = _run_candidate_cli(
        tmp_path, candidate_threshold=True,
    )

    assert completed.returncode != 0
    assert not output_path.exists()
    assert "new_buy_volume_threshold mismatch" in completed.stderr


def test_candidate_cli_rejects_non_t1_volume_audit_signal_date(tmp_path):
    completed, output_path = _run_candidate_cli(
        tmp_path, candidate_audit_signal_date="2019-01-02",
    )

    assert completed.returncode != 0
    assert not output_path.exists()
    assert "volume eligibility signal date is not T-1" in completed.stderr
