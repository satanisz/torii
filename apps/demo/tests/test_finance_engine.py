"""SPEC-0019 F01-F05: arithmetic fixtures, validation and real worker checks."""

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from decimal import Decimal, localcontext

import pytest

from torii_demo.finance_engine import build_manifest, calculate, synthetic_snapshot
from torii_demo.store import encode


def scenario(shock=100, beta=0.35, issues=False):
    return {"shock_bps": shock, "deposit_beta": beta, "inject_issues": issues}


def single_position(*, side="asset", rate=0.1, floor=0, rate_type="floating", repricing=1):
    data = synthetic_snapshot()
    position = {
        "id": "one",
        "name": "Hand calculation",
        "gl_account": "100",
        "side": side,
        "balance_pln": 365_000,
        "annual_rate": rate,
        "rate_type": rate_type,
        "repricing_month": repricing,
        "deposit_beta_applies": False,
        "rate_floor": floor,
    }
    data["positions"] = [position]
    data["ledger"] = [{"gl_account": "100", "side": side, "balance_pln": 365_000}]
    return data


def test_f01_samples_and_manifests_are_stable_independent_and_canonical():
    clean, issues = synthetic_snapshot(), synthetic_snapshot(True)
    assert clean == synthetic_snapshot()
    assert issues == synthetic_snapshot(True)
    clean_manifest = build_manifest(clean, scenario())
    assert clean_manifest == build_manifest(clean, scenario())
    assert clean_manifest["input_sha256"] != build_manifest(issues, scenario())["input_sha256"]
    assert clean_manifest["input_sha256"] == hashlib.sha256(encode(clean).encode()).hexdigest()
    assert (
        clean_manifest["scenario_sha256"] == hashlib.sha256(encode(scenario()).encode()).hexdigest()
    )
    assert len(clean_manifest["engine_sha256"]) == 64
    assert (
        clean_manifest["scenario_sha256"] != build_manifest(clean, scenario(0))["scenario_sha256"]
    )
    report = calculate(clean, scenario())
    report["snapshot"]["positions"][0]["name"] = "changed"
    report["scenario"]["shock_bps"] = -300
    report["assumptions"].clear()
    assert clean == synthetic_snapshot()
    assert calculate(clean, scenario())["assumptions"]
    json.dumps(report, allow_nan=False)


def test_f02_act365_months_and_annual_totals_are_hand_calculated():
    report = calculate(single_position(), scenario(100))
    october, november, february = report["monthly"][0], report["monthly"][1], report["monthly"][4]
    assert october["income_base_pln"] == 3_100
    assert october["income_scenario_pln"] == 3_410
    assert november["income_base_pln"] == 3_000
    assert february["income_base_pln"] == 2_800
    assert report["monthly"][-1]["month"] == "2027-09"
    assert report["totals"] == {
        "income_base_pln": 36_500,
        "expense_base_pln": 0,
        "nii_base_pln": 36_500,
        "income_scenario_pln": 40_150,
        "expense_scenario_pln": 0,
        "nii_scenario_pln": 40_150,
        "delta_nii_pln": 3_650,
    }


def test_f02_liability_sign_delayed_repricing_and_fixed_coupon():
    report = calculate(single_position(side="liability", repricing=3), scenario(100))
    assert report["monthly"][0]["delta_nii_pln"] == 0
    assert report["monthly"][1]["delta_nii_pln"] == 0
    assert report["monthly"][2]["delta_nii_pln"] == -310
    assert report["totals"]["expense_base_pln"] == 36_500
    assert report["totals"]["nii_base_pln"] == -36_500
    assert report["totals"]["delta_nii_pln"] == -3_040
    assert report["contributions"][0]["base_interest_pln"] == 36_500
    assert report["contributions"][0]["delta_nii_pln"] == -3_040
    fixed = calculate(single_position(rate_type="fixed"), scenario(300))
    assert fixed["totals"]["delta_nii_pln"] == 0


@pytest.mark.parametrize(("beta", "delta"), [(0, 0), (0.35, -1_277.5), (1, -3_650)])
def test_f02_deposit_beta_and_floor(beta, delta):
    data = single_position(side="liability", rate=0.02)
    data["positions"][0]["deposit_beta_applies"] = True
    report = calculate(data, scenario(100, beta))
    assert report["totals"]["delta_nii_pln"] == delta
    floor = calculate(data, scenario(-300, 1))
    assert floor["totals"]["expense_scenario_pln"] == 0
    assert floor["totals"]["delta_nii_pln"] == 7_300
    assert {row["scenario_rate"] for row in floor["contributions"][0]["monthly"]} == {0}


def test_f02_round_half_up_per_position_month_then_sum_not_annual_rounding():
    data = single_position(rate=0.5, rate_type="fixed")
    data["positions"][0]["balance_pln"] = 3.65
    data["ledger"][0]["balance_pln"] = 3.65
    # 31 days = 0.155 -> 0.16, 30 = 0.15, February = 0.14. Annual sum = 1.86.
    report = calculate(data, scenario(0))
    assert report["monthly"][0]["income_base_pln"] == 0.16
    assert report["totals"]["income_base_pln"] == 1.86
    assert report["totals"]["delta_nii_pln"] == 0


def test_f02_zero_shock_and_aggregates_match_both_decompositions():
    zero = calculate(synthetic_snapshot(), scenario(0))
    assert zero["totals"]["delta_nii_pln"] == 0
    assert all(row["delta_nii_pln"] == 0 for row in zero["monthly"])
    report = calculate(synthetic_snapshot(), scenario())
    for key, total in report["totals"].items():
        assert Decimal(str(total)) == sum(Decimal(str(row[key])) for row in report["monthly"])
    assert Decimal(str(report["totals"]["delta_nii_pln"])) == sum(
        Decimal(str(row["delta_nii_pln"])) for row in report["contributions"]
    )
    with localcontext() as context:
        context.prec = 6
        # A caller's low-precision context must not change financial arithmetic.
        assert calculate(synthetic_snapshot(), scenario()) == report


def test_f03_reconciliation_supports_shared_accounts_and_union_of_keys():
    data = single_position()
    second = deepcopy(data["positions"][0])
    second["id"] = "two"
    data["positions"].append(second)
    data["ledger"][0]["balance_pln"] *= 2
    assert calculate(data, scenario())["quality_status"] == "passed"
    data["ledger"][0]["gl_account"] = "999"
    report = calculate(data, scenario())
    assert report["quality_status"] == "blocked"
    assert {(row["gl_account"], row["difference_pln"]) for row in report["reconciliation"]} == {
        ("100", 730_000),
        ("999", -730_000),
    }
    # Same account number on two sides is not a duplicate ledger entry.
    data["ledger"].append({"gl_account": "999", "side": "liability", "balance_pln": 20})
    assert len(calculate(data, scenario())["reconciliation"]) == 3


@pytest.mark.parametrize(("difference", "status"), [(0.01, "passed"), (0.02, "blocked")])
def test_f03_reconciliation_one_cent_tolerance(difference, status):
    data = single_position()
    data["ledger"][0]["balance_pln"] += difference
    assert calculate(data, scenario())["quality_status"] == status


def test_f03_f04_injected_issues_block_quality_without_preventing_projection():
    clean = calculate(synthetic_snapshot(), scenario())
    injected = calculate(synthetic_snapshot(True), scenario(issues=True))
    assert clean["quality_status"] == "passed"
    assert clean["anomalies"] == []
    assert injected["quality_status"] == "blocked"
    assert injected["monthly"] == clean["monthly"]
    mismatches = [row for row in injected["reconciliation"] if row["status"] == "mismatch"]
    assert len(mismatches) == 1
    assert mismatches[0]["difference_pln"] == -1_250_000
    assert [item["month"] for item in injected["anomalies"]] == ["2026-08"]
    assert injected["anomalies"][0]["deviation_pln"] < -600_000


def test_f04_only_preceding_six_months_define_baseline_and_threshold():
    data = synthetic_snapshot()
    # First six NII values: 0,100k,200k,300k,400k,500k. Median250k; MAD150k.
    for index, row in enumerate(data["history"]):
        row["interest_expense_pln"] = 0
        row["interest_income_pln"] = index * 100_000 if index < 6 else 250_000
    data["history"][6]["interest_income_pln"] = 1_000_000
    report = calculate(data, scenario())
    first = report["anomalies"][0]
    assert first == {
        "month": "2026-04",
        "nii_pln": 1_000_000,
        "baseline_pln": 250_000,
        "threshold_pln": 667_170,
        "deviation_pln": 750_000,
    }
    data["history"][-1]["interest_income_pln"] = 1e12
    assert calculate(data, scenario())["anomalies"][0] == first
    assert all(row["month"] >= "2026-04" for row in report["anomalies"])


def test_f04_exact_threshold_is_not_an_anomaly_and_zero_mad_uses_floor():
    data = synthetic_snapshot()
    for row in data["history"]:
        row["interest_income_pln"] = 200_000
        row["interest_expense_pln"] = 100_000
    data["history"][6]["interest_income_pln"] = 300_000
    assert calculate(data, scenario())["anomalies"] == []
    data["history"][6]["interest_income_pln"] = 300_000.01
    anomaly = calculate(data, scenario())["anomalies"][0]
    assert anomaly["threshold_pln"] == 100_000
    assert anomaly["deviation_pln"] == 100_000.01


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(currency="EUR"),
        lambda d: d.update(as_of="2026-10-01"),
        lambda d: d.update(extra="field"),
        lambda d: d.update(positions=[]),
        lambda d: d.update(ledger=[]),
        lambda d: d["positions"].append(deepcopy(d["positions"][0])),
        lambda d: d["ledger"].append(deepcopy(d["ledger"][0])),
        lambda d: d["positions"][0].update(balance_pln=float("nan")),
        lambda d: d["positions"][0].update(balance_pln=float("inf")),
        lambda d: d["positions"][0].update(balance_pln=True),
        lambda d: d["positions"][0].update(balance_pln=-1),
        lambda d: d["positions"][0].update(balance_pln=1e13),
        lambda d: d["positions"][0].update(annual_rate="0.1"),
        lambda d: d["positions"][0].update(annual_rate=1.1),
        lambda d: d["positions"][0].update(rate_floor=0.5),
        lambda d: d["positions"][0].update(side="debit"),
        lambda d: d["positions"][0].update(rate_type="unknown"),
        lambda d: d["positions"][0].update(id=" "),
        lambda d: d["positions"][0].update(name="x" * 101),
        lambda d: d["positions"][0].update(repricing_month=True),
        lambda d: d["positions"][0].update(repricing_month=0),
        lambda d: d["positions"][0].update(repricing_month=13),
        lambda d: d["positions"][0].update(deposit_beta_applies=True),
        lambda d: d["positions"][3].update(rate_type="fixed"),
        lambda d: d["positions"][3].update(deposit_beta_applies=1),
        lambda d: d["history"].pop(),
        lambda d: d["history"][0].update(month="2025-11"),
        lambda d: d["history"][0].pop("interest_income_pln"),
        lambda d: d["history"][0].update(interest_expense_pln=-1),
        lambda d: d["ledger"][0].update(balance_pln=float("nan")),
    ],
)
def test_f03_invalid_snapshot_is_rejected_before_hash_or_calculation(change):
    data = synthetic_snapshot()
    change(data)
    with pytest.raises(ValueError):
        build_manifest(data, scenario())
    with pytest.raises(ValueError):
        calculate(data, scenario())


@pytest.mark.parametrize(
    "parameters",
    [
        scenario(True),
        scenario(1.5),
        scenario(301),
        scenario(-301),
        scenario(beta=True),
        scenario(beta=-0.01),
        scenario(beta=1.01),
        scenario(beta=float("nan")),
        scenario(issues=1),
        {"shock_bps": 0, "deposit_beta": 0.35},
        scenario() | {"unknown": 1},
    ],
)
def test_f03_invalid_scenario_rejected(parameters):
    with pytest.raises(ValueError):
        calculate(synthetic_snapshot(), parameters)


def test_f03_position_and_account_limits():
    data = synthetic_snapshot()
    data["positions"] = [dict(data["positions"][0], id=str(index)) for index in range(101)]
    with pytest.raises(ValueError):
        calculate(data, scenario())
    data = synthetic_snapshot()
    data["ledger"] = [dict(data["ledger"][0], gl_account=str(index)) for index in range(101)]
    with pytest.raises(ValueError):
        calculate(data, scenario())


def run_cli(job_path):
    return subprocess.run(
        [sys.executable, "-m", "torii_demo.finance_engine", str(job_path)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def test_f05_real_cli_matches_engine_and_never_overwrites_output(tmp_path):
    output = tmp_path / "result.json"
    job = {"snapshot": synthetic_snapshot(), "scenario": scenario(), "output_path": str(output)}
    path = tmp_path / "job.json"
    path.write_text(encode(job), encoding="utf-8")
    result = run_cli(path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""
    assert json.loads(output.read_text(encoding="utf-8")) == calculate(
        job["snapshot"], job["scenario"]
    )
    original = output.read_bytes()
    rerun = run_cli(path)
    assert rerun.returncode == 1
    assert "Traceback" not in rerun.stderr
    assert output.read_bytes() == original


@pytest.mark.parametrize("output_kind", ["relative", "other-directory", "existing-file"])
def test_f05_cli_refuses_unowned_output_paths(tmp_path, output_kind):
    output = tmp_path / "result.json"
    if output_kind == "relative":
        output = "relative.json"
    elif output_kind == "other-directory":
        output = tmp_path.parent / "finance-result-must-not-be-written.json"
    else:
        output.write_text("preserve", encoding="utf-8")
    path = tmp_path / "job.json"
    path.write_text(
        encode(
            {
                "snapshot": synthetic_snapshot(),
                "scenario": scenario(),
                "output_path": str(output),
            }
        ),
        encoding="utf-8",
    )
    result = run_cli(path)
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    if output_kind == "existing-file":
        assert output.read_text(encoding="utf-8") == "preserve"


def test_f05_cli_invalid_inputs_do_not_publish_partial_result_or_raw_error(tmp_path):
    job = {
        "snapshot": synthetic_snapshot(),
        "scenario": scenario(),
        "output_path": str(tmp_path / "result.json"),
    }
    job["scenario"]["deposit_beta"] = "SECRET_INVALID_VALUE"
    path = tmp_path / "job.json"
    path.write_text(encode(job), encoding="utf-8")
    result = run_cli(path)
    assert result.returncode == 1
    assert "SECRET_INVALID_VALUE" not in result.stderr
    assert not (tmp_path / "result.json").exists()
