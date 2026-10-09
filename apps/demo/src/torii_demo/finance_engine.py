"""SPEC-0019 F01-F04: synthetic NII scenarios and ledger reconciliation.

This deterministic educational calculation is not a regulatory ALM model,
an accounting system, a statistical forecast, or a bank's net profit.
"""

import calendar
import hashlib
import json
import sys
from copy import deepcopy
from decimal import ROUND_HALF_UP, Decimal, localcontext
from pathlib import Path
from statistics import median
from typing import Any

from torii_demo.store import encode

ENGINE_VERSION = "1.0.0"
CENT = Decimal("0.01")
LIMIT = Decimal("1e12")
HISTORY_MONTHS = tuple(f"2025-{month:02d}" for month in range(10, 13)) + tuple(
    f"2026-{month:02d}" for month in range(1, 10)
)
FORECAST_MONTHS = tuple((2026, month) for month in range(10, 13)) + tuple(
    (2027, month) for month in range(1, 10)
)
TOTAL_FIELDS = (
    "income_base_pln",
    "expense_base_pln",
    "nii_base_pln",
    "income_scenario_pln",
    "expense_scenario_pln",
    "nii_scenario_pln",
    "delta_nii_pln",
)
ASSUMPTIONS = [
    "Wyłącznie dane syntetyczne; wycinek portfeli i księgi, nie pełny bilans banku.",
    "NII = przychody odsetkowe minus koszty odsetkowe; NII nie jest zyskiem netto.",
    "Projekcja warunkowa na 2026-10-01–2027-10-01, PLN, ACT/365F, stałe salda.",
    "Brak zapadalności, nowej sprzedaży, amortyzacji, opcji, FX i hedgingu.",
    "Brak EIR/IFRS9 oraz modeli behawioralnych depozytów; to nie pomiar IRRBB.",
    "Szok równoległy stosowany od początku miesiąca repricing; nie jest szokiem nadzorczym.",
    "Beta dotyczy wyłącznie zmiennoprocentowych depozytów oznaczonych w danych.",
    "Odsetki zaokrąglane HALF_UP do grosza dla każdej pozycji i miesiąca, potem sumowane.",
    "Reguła anomalii: poprzednie 6 miesięcy; pierwsze 6 służy tylko jako okno bazowe.",
    "Sygnał anomalii wymaga weryfikacji; nie jest modelem ML ani dowodem błędu.",
    "Niezgodne uzgodnienie blokuje jakość wyniku, lecz pozwala na roboczą eksplorację.",
]


def _object(value: Any, fields: set[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        raise ValueError("Invalid finance object fields")
    return value


def _text(value: Any) -> None:
    if type(value) is not str or not value.strip() or not 1 <= len(value) <= 100:
        raise ValueError("Invalid finance identifier or name")


def _number(value: Any, minimum: Decimal = Decimal(0), maximum: Decimal = LIMIT) -> Decimal:
    if type(value) not in (int, float):
        raise ValueError("Finance values must be finite JSON numbers")
    number = Decimal(str(value))
    if not number.is_finite() or not minimum <= number <= maximum:
        raise ValueError("Finance number is outside its permitted range")
    return number


def _side(value: Any) -> None:
    if type(value) is not str or value not in ("asset", "liability"):
        raise ValueError("Invalid finance side")


def _validate(snapshot: Any, scenario: Any) -> None:
    _object(snapshot, {"as_of", "currency", "positions", "ledger", "history"})
    if snapshot["as_of"] != "2026-09-30" or snapshot["currency"] != "PLN":
        raise ValueError("Finance snapshot requires 2026-09-30 and PLN")
    _object(scenario, {"shock_bps", "deposit_beta", "inject_issues"})
    if type(scenario["shock_bps"]) is not int or not -300 <= scenario["shock_bps"] <= 300:
        raise ValueError("Shock must be an integer from -300 to 300 basis points")
    _number(scenario["deposit_beta"], maximum=Decimal(1))
    if type(scenario["inject_issues"]) is not bool:
        raise ValueError("Issue selection must be boolean")
    for key in ("positions", "ledger"):
        if type(snapshot[key]) is not list or not 1 <= len(snapshot[key]) <= 100:
            raise ValueError("Finance snapshot requires 1 to 100 positions and ledger accounts")
    position_ids: set[str] = set()
    for position in snapshot["positions"]:
        _object(
            position,
            {
                "id",
                "name",
                "gl_account",
                "side",
                "balance_pln",
                "annual_rate",
                "rate_type",
                "repricing_month",
                "deposit_beta_applies",
                "rate_floor",
            },
        )
        for key in ("id", "name", "gl_account"):
            _text(position[key])
        if position["id"] in position_ids:
            raise ValueError("Duplicate portfolio position identifier")
        position_ids.add(position["id"])
        _side(position["side"])
        _number(position["balance_pln"])
        rate = _number(position["annual_rate"], Decimal(-1), Decimal(1))
        floor = _number(position["rate_floor"], Decimal(-1), Decimal(1))
        if rate < floor:
            raise ValueError("Annual rate must not be below its floor")
        if type(position["rate_type"]) is not str or position["rate_type"] not in (
            "fixed",
            "floating",
        ):
            raise ValueError("Invalid rate type")
        if (
            type(position["repricing_month"]) is not int
            or not 1 <= position["repricing_month"] <= 12
        ):
            raise ValueError("Repricing month must be an integer from 1 to 12")
        if type(position["deposit_beta_applies"]) is not bool:
            raise ValueError("Deposit beta selection must be boolean")
        if position["deposit_beta_applies"] and (
            position["side"] != "liability" or position["rate_type"] != "floating"
        ):
            raise ValueError("Deposit beta applies only to floating liabilities")
    ledger_keys: set[tuple[str, str]] = set()
    for row in snapshot["ledger"]:
        _object(row, {"gl_account", "side", "balance_pln"})
        _text(row["gl_account"])
        _side(row["side"])
        _number(row["balance_pln"])
        key = (row["gl_account"], row["side"])
        if key in ledger_keys:
            raise ValueError("Duplicate ledger account and side")
        ledger_keys.add(key)
    history = snapshot["history"]
    if type(history) is not list or len(history) != 12:
        raise ValueError("History requires twelve consecutive months")
    for expected, row in zip(HISTORY_MONTHS, history, strict=True):
        _object(row, {"month", "interest_income_pln", "interest_expense_pln"})
        if row["month"] != expected:
            raise ValueError("History months must be ordered from 2025-10 through 2026-09")
        _number(row["interest_income_pln"])
        _number(row["interest_expense_pln"])


def build_manifest(snapshot: dict[str, Any], scenario: dict[str, Any]) -> dict[str, str]:
    """F01: validate and fingerprint the exact inputs and this engine's source."""
    _validate(snapshot, scenario)
    return {
        "engine_version": ENGINE_VERSION,
        "engine_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "input_sha256": hashlib.sha256(encode(snapshot).encode("utf-8")).hexdigest(),
        "scenario_sha256": hashlib.sha256(encode(scenario).encode("utf-8")).hexdigest(),
    }


def synthetic_snapshot(inject_issues: bool = False) -> dict[str, Any]:
    """F01/F03/F04: reproducible aggregate positions, ledger and historical NII."""
    if type(inject_issues) is not bool:
        raise ValueError("Issue selection must be boolean")
    seeds = (
        (
            "loans-fixed",
            "Kredyty — stała stopa",
            "110100",
            "asset",
            300_000_000,
            0.06,
            "fixed",
            1,
            False,
        ),
        (
            "loans-floating",
            "Kredyty — zmienna stopa",
            "110200",
            "asset",
            250_000_000,
            0.07,
            "floating",
            1,
            False,
        ),
        (
            "bonds-fixed",
            "Obligacje — stała stopa",
            "120100",
            "asset",
            200_000_000,
            0.042,
            "fixed",
            1,
            False,
        ),
        (
            "savings",
            "Depozyty oszczędnościowe",
            "210100",
            "liability",
            400_000_000,
            0.02,
            "floating",
            1,
            True,
        ),
        (
            "term-deposits",
            "Depozyty terminowe",
            "210200",
            "liability",
            250_000_000,
            0.038,
            "fixed",
            1,
            False,
        ),
        (
            "wholesale",
            "Finansowanie hurtowe",
            "220100",
            "liability",
            100_000_000,
            0.05,
            "floating",
            3,
            False,
        ),
    )
    positions = [
        {
            "id": identifier,
            "name": name,
            "gl_account": account,
            "side": side,
            "balance_pln": balance,
            "annual_rate": rate,
            "rate_type": rate_type,
            "repricing_month": repricing,
            "deposit_beta_applies": beta,
            "rate_floor": 0,
        }
        for identifier, name, account, side, balance, rate, rate_type, repricing, beta in seeds
    ]
    ledger = [
        {key: position[key] for key in ("gl_account", "side", "balance_pln")}
        for position in positions
    ]
    history = [
        {
            "month": month,
            "interest_income_pln": 3_650_000 + (index % 4) * 15_000,
            "interest_expense_pln": 1_850_000 + (index % 3) * 8_000,
        }
        for index, month in enumerate(HISTORY_MONTHS)
    ]
    if inject_issues:
        ledger[0]["balance_pln"] += 1_250_000
        history[10]["interest_expense_pln"] += 650_000
    return {
        "as_of": "2026-09-30",
        "currency": "PLN",
        "positions": positions,
        "ledger": ledger,
        "history": history,
    }


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _reconcile(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    portfolios: dict[tuple[str, str], Decimal] = {}
    ledger: dict[tuple[str, str], Decimal] = {}
    for position in snapshot["positions"]:
        key = (position["gl_account"], position["side"])
        portfolios[key] = portfolios.get(key, Decimal(0)) + Decimal(str(position["balance_pln"]))
    for row in snapshot["ledger"]:
        ledger[row["gl_account"], row["side"]] = Decimal(str(row["balance_pln"]))
    results = []
    for account, side in sorted(portfolios.keys() | ledger.keys()):
        key = (account, side)
        portfolio_balance = portfolios.get(key, Decimal(0))
        ledger_balance = ledger.get(key, Decimal(0))
        difference = portfolio_balance - ledger_balance
        results.append(
            {
                "gl_account": account,
                "side": side,
                "portfolio_pln": portfolio_balance,
                "ledger_pln": ledger_balance,
                "difference_pln": difference,
                "status": "matched" if abs(difference) <= CENT else "mismatch",
            }
        )
    return results


def _anomalies(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = [
        Decimal(str(row["interest_income_pln"])) - Decimal(str(row["interest_expense_pln"]))
        for row in history
    ]
    anomalies = []
    for index in range(6, len(values)):
        window = values[index - 6 : index]
        baseline = median(window)
        mad = median([abs(value - baseline) for value in window])
        threshold = max(Decimal(100_000), Decimal(3) * Decimal("1.4826") * mad)
        deviation = values[index] - baseline
        if abs(deviation) > threshold:
            anomalies.append(
                {
                    "month": history[index]["month"],
                    "nii_pln": values[index],
                    "baseline_pln": baseline,
                    "threshold_pln": threshold,
                    "deviation_pln": deviation,
                }
            )
    return anomalies


def _contribution(position: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    balance = Decimal(str(position["balance_pln"]))
    annual_rate = Decimal(str(position["annual_rate"]))
    floor = Decimal(str(position["rate_floor"]))
    beta = (
        Decimal(str(scenario["deposit_beta"])) if position["deposit_beta_applies"] else Decimal(1)
    )
    shock = Decimal(scenario["shock_bps"]) / Decimal(10_000)
    monthly = []
    for index, (year, month) in enumerate(FORECAST_MONTHS, start=1):
        base_rate = scenario_rate = annual_rate
        if position["rate_type"] == "floating" and index >= position["repricing_month"]:
            base_rate = max(floor, annual_rate)
            scenario_rate = max(floor, annual_rate + shock * beta)
        days = Decimal(calendar.monthrange(year, month)[1])
        monthly.append(
            {
                "month": f"{year}-{month:02d}",
                "base_rate": base_rate,
                "scenario_rate": scenario_rate,
                "base_interest_pln": _money(balance * base_rate * days / Decimal(365)),
                "scenario_interest_pln": _money(balance * scenario_rate * days / Decimal(365)),
            }
        )
    base_interest = sum((row["base_interest_pln"] for row in monthly), Decimal(0))
    scenario_interest = sum((row["scenario_interest_pln"] for row in monthly), Decimal(0))
    sign = Decimal(1) if position["side"] == "asset" else Decimal(-1)
    return {
        "position_id": position["id"],
        "name": position["name"],
        "side": position["side"],
        "balance_pln": balance,
        "rate_type": position["rate_type"],
        "repricing_month": position["repricing_month"],
        "base_interest_pln": base_interest,
        "scenario_interest_pln": scenario_interest,
        "delta_nii_pln": sign * (scenario_interest - base_interest),
        "monthly": monthly,
    }


def _json_numbers(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _json_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_numbers(item) for item in value]
    return value


def calculate(snapshot: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    """F01-F04: return an independent, JSON-serializable report for explicit inputs."""
    manifest = build_manifest(snapshot, scenario)
    with localcontext() as context:
        context.prec = 50
        contributions = [_contribution(position, scenario) for position in snapshot["positions"]]
        monthly = []
        for index, (year, month) in enumerate(FORECAST_MONTHS):
            row: dict[str, Any] = {"month": f"{year}-{month:02d}"}
            for variant in ("base", "scenario"):
                for side, kind in (("asset", "income"), ("liability", "expense")):
                    row[f"{kind}_{variant}_pln"] = sum(
                        (
                            item["monthly"][index][f"{variant}_interest_pln"]
                            for item in contributions
                            if item["side"] == side
                        ),
                        Decimal(0),
                    )
                row[f"nii_{variant}_pln"] = (
                    row[f"income_{variant}_pln"] - row[f"expense_{variant}_pln"]
                )
            row["delta_nii_pln"] = row["nii_scenario_pln"] - row["nii_base_pln"]
            monthly.append(row)
        totals = {key: sum((row[key] for row in monthly), Decimal(0)) for key in TOTAL_FIELDS}
        reconciliation = _reconcile(snapshot)
        report = {
            "snapshot": deepcopy(snapshot),
            "scenario": deepcopy(scenario),
            "manifest": manifest,
            "assumptions": list(ASSUMPTIONS),
            "quality_status": (
                "passed" if all(row["status"] == "matched" for row in reconciliation) else "blocked"
            ),
            "reconciliation": reconciliation,
            "anomalies": _anomalies(snapshot["history"]),
            "monthly": monthly,
            "contributions": contributions,
            "totals": totals,
        }
        return _json_numbers(report)


def _reject_constant(_value: str) -> None:
    raise ValueError("Non-finite JSON constant")


def main() -> int:
    """F05: fixed-module worker; paths come from the local orchestrator only."""
    try:
        if len(sys.argv) != 2:
            raise ValueError("One internal job file is required")
        job_path = Path(sys.argv[1])
        if job_path.is_symlink() or not job_path.is_file():
            raise ValueError("Invalid internal job file")
        job_path = job_path.resolve(strict=True)
        if job_path.stat().st_size > 1024 * 1024:
            raise ValueError("Internal finance job is too large")
        job = json.loads(job_path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
        _object(job, {"snapshot", "scenario", "output_path"})
        if type(job["output_path"]) is not str:
            raise ValueError("Invalid output path")
        output = Path(job["output_path"])
        if (
            not output.is_absolute()
            or output.is_symlink()
            or output.exists()
            or output.parent != job_path.parent
            or output.parent.resolve(strict=True) != job_path.parent
        ):
            raise ValueError("Output must be a new file in the internal job directory")
        report = calculate(job["snapshot"], job["scenario"])
        with output.open("x", encoding="utf-8") as stream:
            stream.write(encode(report))
        return 0
    except Exception:
        print("Local finance calculation failed; check inputs and local storage.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
