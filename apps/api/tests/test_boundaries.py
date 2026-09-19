"""SPEC-0002 AC-04 import boundaries and executable contract anchors."""

import ast
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from torii_api.domain.errors import DomainError
from torii_api.http.problems import problem

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = Path(__file__).resolve().parents[1] / "src" / "torii_api"
ML_ROOTS = {"torch", "tensorflow", "autogluon", "mlflow", "sklearn", "pandas", "numpy"}


def test_api_never_imports_workload_libraries() -> None:
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports = [name.name for name in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [node.module or ""]
            else:
                continue
            for name in imports:
                assert name.split(".")[0] not in ML_ROOTS, (path, name)
                if "domain" in path.parts:
                    assert (
                        name.startswith("torii_api.domain")
                        or name.split(".")[0] in sys.stdlib_module_names
                    ), (path, name)


def test_error_response_matches_canonical_contract() -> None:
    contract = json.loads(
        (ROOT / "specs/0001-project-object-version/contracts/openapi.json").read_text(
            encoding="utf-8"
        )
    )
    response = problem(
        DomainError(422, "validation_failed", ("/name",)), "2025b336-ce3c-4bcf-8766-6b5d13f0a044"
    )
    Draft202012Validator(
        contract["components"]["schemas"]["Problem"], format_checker=FormatChecker()
    ).validate(json.loads(response.body))


def test_migration_head_matches_readiness() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from torii_api.storage.database import SCHEMA_HEAD

    config = Config(str(PACKAGE.parents[1] / "alembic.ini"))
    assert ScriptDirectory.from_config(config).get_heads() == [SCHEMA_HEAD]
