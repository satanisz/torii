"""Pure leakage/reproducibility checks; these do not qualify real MLflow or ACL."""

import importlib.util
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SPEC = importlib.util.spec_from_file_location(
    "torii_exp03_train", Path(__file__).with_name("train.py")
)
assert SPEC is not None and SPEC.loader is not None
worker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = worker
SPEC.loader.exec_module(worker)


def prepared(seed=42):
    content = worker.csv_bytes(worker.generate_monthly_data(seed))
    raw = pd.read_csv(io.BytesIO(content), float_precision="round_trip")
    supervised = worker.build_supervised(raw)
    return content, raw, supervised, worker.chronological_split(supervised)


def test_next_month_label_and_strict_chronological_gap():
    _, raw, supervised, (train, test, split) = prepared()
    indexed = raw.set_index("month")
    assert worker.TARGET not in worker.FEATURES
    for row in supervised.to_dict("records"):
        assert (
            row[worker.TARGET] == indexed.loc[row["target_month"], "accounting_profit"]
        )
        assert (
            row["profit_current"]
            == indexed.loc[row["origin_month"], "accounting_profit"]
        )
        assert row["origin_month"] < row["target_month"]
    assert train["target_month"].max() < test["origin_month"].min()
    assert len(train) + len(test) + split["gap_rows"] == len(supervised)
    assert set(train["origin_month"]).isdisjoint(test["origin_month"])
    assert not split["shuffle"]


def test_future_financial_values_cannot_change_past_features():
    _, raw, supervised, _ = prepared()
    changed = raw.copy()
    cutoff = raw.loc[75, "month"]
    changed.loc[76:, changed.columns != "month"] += 1_000_000
    after = worker.build_supervised(changed)
    mask = supervised["origin_month"] <= cutoff
    pd.testing.assert_frame_equal(
        supervised.loc[mask, worker.FEATURES], after.loc[mask, worker.FEATURES]
    )
    # The label for the cutoff row SHOULD change: it explicitly belongs to the future.
    cutoff_row = supervised["origin_month"] == cutoff
    assert not supervised.loc[cutoff_row, worker.TARGET].equals(
        after.loc[cutoff_row, worker.TARGET]
    )


def test_test_values_cannot_change_fitted_scaler_or_model():
    _, _, _, (train, test, _) = prepared()
    first = worker.fit_candidates(train, test)
    changed = test.copy()
    changed[worker.FEATURES] += 500_000
    changed[worker.TARGET] -= 500_000
    second = worker.fit_candidates(train, changed)
    scaler = first["ridge"]["model"].named_steps["scaler"]
    np.testing.assert_allclose(scaler.mean_, train[worker.FEATURES].mean().to_numpy())
    np.testing.assert_array_equal(
        scaler.mean_, second["ridge"]["model"].named_steps["scaler"].mean_
    )
    np.testing.assert_array_equal(
        first["ridge"]["model"].named_steps["model"].coef_,
        second["ridge"]["model"].named_steps["model"].coef_,
    )
    np.testing.assert_allclose(
        first["dummy"]["predictions"]["predicted"], train[worker.TARGET].mean()
    )


def test_same_seed_reproduces_data_predictions_and_metrics_changed_seed_does_not():
    bytes1, _, _, (train1, test1, _) = prepared(42)
    bytes2, _, _, (train2, test2, _) = prepared(42)
    bytes3, _, _, _ = prepared(43)
    assert worker.digest(bytes1) == worker.digest(bytes2)
    assert worker.digest(bytes1) != worker.digest(bytes3)
    first, second = (
        worker.fit_candidates(train1, test1),
        worker.fit_candidates(train2, test2),
    )
    for algorithm in ("dummy", "ridge"):
        assert first[algorithm]["metrics"] == second[algorithm]["metrics"]
        assert worker.digest(
            worker.csv_bytes(first[algorithm]["predictions"])
        ) == worker.digest(worker.csv_bytes(second[algorithm]["predictions"]))


def test_logged_transform_source_replays_exact_feature_and_split_contract():
    _, raw, supervised, (_, _, split) = prepared()
    namespace = {}
    # Execute only this checked-in module's own source extraction, never external code.
    exec(compile(worker.transform_source(), "logged-transform.py", "exec"), namespace)  # noqa: S102
    replayed = namespace["build_supervised"](raw)
    pd.testing.assert_frame_equal(replayed, supervised)
    assert namespace["chronological_split"](replayed)[2] == split


@pytest.mark.parametrize(
    "uri",
    [
        "s3://bucket/path",
        "file:///tmp/a",
        "http://mlflow:5000/a",
        "mlflow-artifacts://other:5000/a",
    ],
)
def test_direct_storage_or_foreign_proxy_uri_is_not_allowed(uri):
    assert not worker.proxy_artifact_uri(uri)


def test_proxy_artifact_paths_supported():
    assert worker.proxy_artifact_uri("mlflow-artifacts:/1/run/artifacts")
    assert worker.proxy_artifact_uri("mlflow-artifacts://mlflow:5000/1/run/artifacts")


@pytest.mark.parametrize("seed", [-1, 2**32, True])
def test_seed_domain_is_bounded(seed):
    with pytest.raises(ValueError, match="invalid_seed"):
        worker.generate_monthly_data(seed)
