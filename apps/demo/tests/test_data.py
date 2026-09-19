"""SPEC-0018 D01/D02/D06: finite snapshots and immutable transforms."""

import copy
import math

import pytest

from torii_demo.data import parse_csv, synthetic_data, transform


def test_csv_profile_missing_and_utf8_bom():
    data = parse_csv("\ufeffx,label,target\n1,żółć,2\n3,,4\n,other,6\n".encode())
    assert data["columns"] == ["x", "label", "target"]
    assert data["rows"][0] == {"x": 1.0, "label": "żółć", "target": 2.0}
    assert data["row_count"] == 3
    assert data["profile"][0] == {
        "name": "x",
        "dtype": "number",
        "missing": 1,
        "unique": 2,
        "min": 1.0,
        "max": 3.0,
        "mean": 2.0,
    }
    assert data["profile"][1]["missing"] == 1


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"x,x\n1,2",
        b" ,y\n1,2",
        b"x,y\n1",
        b"x\n1,2",
        b"x\n\xff",
        b'x\n"unclosed',
        b"x\nNaN",
        b"x\n-inf",
        b"x\n1e999",
        b"x\n" + b"a" * 2001,
        b"x\n" + b"1\n" * 5001,
    ],
)
def test_bad_csv_is_rejected(body):
    with pytest.raises(ValueError):
        parse_csv(body)


def test_wide_csv_and_long_header_are_rejected():
    with pytest.raises(ValueError):
        parse_csv((",".join(f"c{i}" for i in range(51)) + "\n").encode())
    with pytest.raises(ValueError):
        parse_csv(("x" * 101 + "\n").encode())


@pytest.mark.parametrize(
    "definition,expected",
    [
        ({"operation": "drop_missing"}, [{"x": 1.0, "y": 2.0}, {"x": 1.0, "y": 2.0}]),
        ({"operation": "drop_duplicates"}, [{"x": 1.0, "y": 2.0}, {"x": 3.0, "y": None}]),
        ({"operation": "select_columns", "columns": ["y"]}, [{"y": 2.0}, {"y": 2.0}, {"y": None}]),
        (
            {"operation": "filter_numeric", "column": "x", "operator": "gte", "value": 2},
            [{"x": 3.0, "y": None}],
        ),
    ],
)
def test_transform_is_new_snapshot_without_input_mutation(definition, expected):
    original = parse_csv(b"x,y\n1,2\n1,2\n3,\n")
    before = copy.deepcopy(original)
    result = transform(original, definition)
    assert original == before
    assert result["rows"] == expected
    assert result is not original
    if result["rows"]:
        result["rows"][0][result["columns"][0]] = "changed"
        assert original == before


@pytest.mark.parametrize(
    "definition",
    [
        {"operation": "eval", "code": "anything"},
        {"operation": "select_columns", "columns": ["x", "x"]},
        {"operation": "select_columns", "columns": []},
        {"operation": "select_columns", "columns": ["unknown"]},
        {"operation": "filter_numeric", "column": "x", "operator": "exec", "value": 1},
        {"operation": "filter_numeric", "column": "x", "operator": "gte", "value": math.inf},
        {"operation": "filter_numeric", "column": "label", "operator": "gte", "value": 1},
    ],
)
def test_bad_transform_is_rejected(definition):
    with pytest.raises(ValueError):
        transform(parse_csv(b"x,label\n1,text\n"), definition)


def test_profile_mean_remains_finite_for_large_finite_values():
    profile = parse_csv(b"x\n1e308\n1e308\n")["profile"][0]
    assert math.isfinite(profile["mean"])


def test_synthetic_is_deterministic_independent_and_trainable_shape():
    first, second = synthetic_data(), synthetic_data()
    assert first == second
    assert first["row_count"] >= 20
    assert first["columns"][-1] == "target"
    assert all(profile["dtype"] == "number" for profile in first["profile"])
    first["rows"][0]["target"] = "changed"
    assert first != second
