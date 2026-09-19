"""SPEC-0018 D01/D02/D06: bounded, finite, immutable table snapshots."""

import csv
import io
import math
import random
from typing import Any

Data = dict[str, Any]


def snapshot(columns: list[str], rows: list[dict[str, Any]]) -> Data:
    """Validate scalar values and recompute metadata; never trust stored profiles."""
    if (
        type(columns) is not list
        or not 1 <= len(columns) <= 50
        or any(type(name) is not str or not name.strip() or len(name) > 100 for name in columns)
        or len(set(columns)) != len(columns)
        or type(rows) is not list
        or len(rows) > 5000
        or len(rows) * len(columns) > 250000
    ):
        raise ValueError("Invalid dataset shape or column names")
    copied = []
    for row in rows:
        if type(row) is not dict or set(row) != set(columns):
            raise ValueError("Every row must match the dataset columns")
        for value in row.values():
            if value is None:
                continue
            if type(value) not in (str, int, float, bool):
                raise ValueError("Dataset values must be JSON scalars")
            if isinstance(value, str) and len(value) > 2000:
                raise ValueError("Dataset text exceeds the size limit")
            if type(value) in (int, float):
                try:
                    finite = math.isfinite(value)
                except OverflowError:
                    finite = False
                if not finite:
                    raise ValueError("Dataset numbers must be finite")
        copied.append(dict(row))
    profile = []
    for name in columns:
        values = [row[name] for row in copied if row[name] is not None]
        kinds = {
            "number"
            if type(value) in (int, float)
            else "boolean"
            if type(value) is bool
            else "string"
            for value in values
        }
        dtype = next(iter(kinds)) if len(kinds) == 1 else "mixed" if kinds else "empty"
        numeric = dtype == "number"
        profile.append(
            {
                "name": name,
                "dtype": dtype,
                "missing": len(copied) - len(values),
                "unique": len({(type(value).__name__, value) for value in values}),
                "min": min(values) if numeric else None,
                "max": max(values) if numeric else None,
                "mean": math.fsum(value / len(values) for value in values) if numeric else None,
            }
        )
    return {"columns": list(columns), "rows": copied, "row_count": len(copied), "profile": profile}


def parse_csv(content: bytes) -> Data:
    if type(content) is not bytes or not content or len(content) > 8 * 1024 * 1024:
        raise ValueError("CSV is empty or exceeds the size limit")
    try:
        reader = csv.reader(io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
        columns = next(reader)
        snapshot(columns, [])
        rows = []
        for record in reader:
            if not record:  # CSV blank physical lines are not data records.
                continue
            if len(record) != len(columns) or len(rows) >= 5000:
                raise ValueError("CSV rows must match the columns and row limit")
            values: list[Any] = []
            for cell in record:
                if len(cell) > 2000:
                    raise ValueError("CSV cell exceeds the size limit")
                if cell == "":
                    values.append(None)
                    continue
                try:
                    number = float(cell)
                except ValueError:
                    values.append(cell)
                else:
                    if not math.isfinite(number):
                        raise ValueError("CSV numbers must be finite")
                    values.append(number)
            rows.append(dict(zip(columns, values, strict=True)))
        return snapshot(columns, rows)
    except (UnicodeError, csv.Error, StopIteration):
        raise ValueError("CSV must be a valid UTF-8 comma-delimited table") from None


def synthetic_data() -> Data:
    generator = random.Random(42)
    rows = []
    for index in range(160):
        x1, x2, x3 = (generator.uniform(-8, 8) for _ in range(3))
        target = 4 * x1 - 2 * x2 + 0.5 * x3 + 10 + generator.gauss(0, 0.7)
        rows.append(
            {
                "x1": round(x1, 4),
                "x2": None if index % 37 == 0 else round(x2, 4),
                "x3": round(x3, 4),
                "target": round(target, 4),
            }
        )
    return snapshot(["x1", "x2", "x3", "target"], rows)


def transform(data: Data, definition: dict[str, Any]) -> Data:
    if type(data) is not dict or type(definition) is not dict:
        raise ValueError("Invalid transformation input")
    source = snapshot(data.get("columns"), data.get("rows"))
    columns, rows = source["columns"], source["rows"]
    operation = definition.get("operation")
    if operation == "drop_missing":
        rows = [row for row in rows if all(value is not None for value in row.values())]
    elif operation == "drop_duplicates":
        seen = set()
        unique = []
        for row in rows:
            key = tuple((type(row[name]).__name__, row[name]) for name in columns)
            if key not in seen:
                seen.add(key)
                unique.append(row)
        rows = unique
    elif operation == "select_columns":
        selected = definition.get("columns")
        if (
            type(selected) is not list
            or not selected
            or any(type(name) is not str or name not in columns for name in selected)
            or len(set(selected)) != len(selected)
        ):
            raise ValueError("Select existing unique columns")
        columns = selected
        rows = [{name: row[name] for name in columns} for row in rows]
    elif operation == "filter_numeric":
        name, operator, value = (definition.get(key) for key in ("column", "operator", "value"))
        if (
            name not in columns
            or operator not in ("gte", "lte")
            or type(value) not in (int, float)
            or not math.isfinite(value)
            or next(item for item in source["profile"] if item["name"] == name)["dtype"] != "number"
        ):
            raise ValueError("Filter requires a numeric column, finite value and gte/lte")
        rows = [
            row
            for row in rows
            if row[name] is not None
            and (row[name] >= value if operator == "gte" else row[name] <= value)
        ]
    else:
        raise ValueError("Unsupported transformation")
    return snapshot(columns, rows)
