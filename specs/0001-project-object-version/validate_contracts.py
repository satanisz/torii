# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "jsonschema==4.25.1",
#   "openapi-spec-validator==0.7.2",
#   "rfc8785==0.1.4",
# ]
# ///
"""Read-only SP-00 contract checks; not product implementation or runtime tests.

Run: uv run --python 3.12 --no-project path/to/validate_contracts.py
Direct tool dependencies are pinned; this is not the production runtime lock.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import rfc8785
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

CONTRACTS = Path(__file__).resolve().parent / "contracts"


def read_json(name: str):
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def main() -> None:
    if not __debug__:
        raise SystemExit("Run without -O: contract assertions must remain enabled")
    schema = read_json("definitions.schema.json")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    api = read_json("openapi.json")
    validate(api, base_uri=(CONTRACTS / "openapi.json").as_uri())

    examples = read_json("examples.json")
    valid = {case["id"]: case["definition"] for case in examples["valid"]}
    assert len(valid) == len(examples["valid"]), "Duplicate example IDs"
    for name, definition in valid.items():
        validator.validate(definition)
        rfc8785.dumps(definition)

    for case in examples["invalid"]:
        candidate = copy.deepcopy(valid[case["base"]])
        parts = case["pointer"].lstrip("/").split("/")
        parent = candidate
        for part in parts[:-1]:
            parent = parent[int(part)] if isinstance(parent, list) else parent[part]
        key = int(parts[-1]) if isinstance(parent, list) else parts[-1]
        if case.get("remove"):
            del parent[key]
        else:
            parent[key] = case["value"]
        assert not validator.is_valid(candidate), f"Invalid fixture accepted: {case['id']}"

    for case in examples["canonical"]:
        actual = rfc8785.dumps(case["definition"])
        expected = case["expected"].encode("utf-8")
        assert actual == expected, f"JCS mismatch: {case['id']}"
        reordered = dict(reversed(list(case["definition"].items())))
        assert rfc8785.dumps(reordered) == expected
        print(f"JCS {case['id']}: sha256={hashlib.sha256(actual).hexdigest()}")

    api_uri = (CONTRACTS / "openapi.json").as_uri()
    registry = Registry().with_resources(
        [
            (api_uri, Resource.from_contents(api, default_specification=DRAFT202012)),
            ((CONTRACTS / "definitions.schema.json").as_uri(), Resource.from_contents(schema)),
        ]
    )
    project = {"name": "Deliveries", "description": "Synthetic fixture"}
    object_create = {**project, "definition": valid["dataset-csv"]}
    policy = {"members": [{"principal_id": "10000000-0000-4000-8000-000000000001", "role": "owner"}]}
    request_cases = [
        ("ProjectCreate", project, True),
        ("ObjectCreate", object_create, True),
        ("DraftWrite", {"definition": valid["transformation-python"]}, True),
        ("AccessPolicyWrite", policy, True),
        ("ProjectCreate", {**project, "owner_id": "injected"}, False),
        ("ObjectCreate", {**object_create, "project_id": "injected"}, False),
        ("MetadataPatch", {}, False),
        ("AccessPolicyWrite", {"members": []}, False),
    ]
    for component, payload, expected_valid in request_cases:
        request_validator = Draft202012Validator(
            {"$ref": f"{api_uri}#/components/schemas/{component}"},
            registry=registry,
            format_checker=FormatChecker(),
        )
        assert request_validator.is_valid(payload) == expected_valid, component

    operations = [
        operation
        for path_item in api["paths"].values()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]
    operation_ids = [operation["operationId"] for operation in operations]
    assert len(operation_ids) == len(set(operation_ids)), "Duplicate operationId"
    assert all(
        set(path_item).isdisjoint({"put", "patch", "delete", "post"})
        for path, path_item in api["paths"].items()
        if path.endswith("/versions/{version_id}")
    ), "Immutable version has a write endpoint"
    for operation in operations:
        assert "default" in operation["responses"]
        if operation["operationId"] not in {"startLogin", "finishLogin"}:
            assert "401" in operation["responses"]

    print(
        f"PASS: OpenAPI 3.1 ({len(operations)} operations), definition schema, "
        f"{len(valid)} valid and {len(examples['invalid'])} invalid fixtures, "
        f"{len(examples['canonical'])} golden JCS vectors, "
        f"{len(request_cases)} API request cases."
    )
    print("NOT RUN: authorization, transactions, migrations, OIDC and UI acceptance tests.")


if __name__ == "__main__":
    main()
