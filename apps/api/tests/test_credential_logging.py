"""SPEC-0001 B2a4b / A4b-05, A4b-06: logging policy and upgrade boundary."""

import ast
import importlib.util
import logging
import traceback
from collections.abc import Iterator
from importlib import metadata
from pathlib import Path

import httpcore
import httpx
import pytest
from httpcore._trace import Trace

from torii_api.domain.errors import DomainError
from torii_api.security import credential_logging as policy

_EXPECTED_LOGGERS = {
    "httpx",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
    "httpcore.socks",
}
_EXPECTED_VERSIONS = {"httpx": "0.28.1", "httpcore": "1.0.9"}
_MARKER = "synthetic-credential-must-not-appear"


@pytest.fixture(autouse=True)
def restore_logging_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Only restore settings these tests can mutate, including preexisting init."""
    names = (*policy.CREDENTIAL_LOGGER_NAMES, "httpcore", "torii.identity", "torii.other")
    loggers = [logging.getLogger(), *(logging.getLogger(name) for name in names)]
    snapshots = [
        (logger, logger.disabled, logger.level, logger.propagate, logger.handlers[:])
        for logger in loggers
    ]
    previous_configured = policy._configured
    previous_disable = logging.root.manager.disable
    monkeypatch.setattr(policy, "_configured", False)
    try:
        yield
    finally:
        for logger, disabled, level, propagate, handlers in snapshots:
            logger.disabled = disabled
            logger.setLevel(level)
            logger.propagate = propagate
            logger.handlers[:] = handlers
        logging.disable(previous_disable)
        policy._configured = previous_configured


def _assert_safe_failure(error: DomainError) -> None:
    assert (error.status, error.code, error.pointers) == (503, "identity_unavailable", ())
    assert error.__cause__ is None
    assert error.__context__ is None
    assert _MARKER not in str(error)
    assert _MARKER not in repr(error)
    assert _MARKER not in "".join(traceback.format_exception(error))


def test_import_does_not_configure_logging_or_inspect_installed_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Import must not inspect package versions or logging configuration")

    spec = importlib.util.spec_from_file_location("credential_logging_import_test", policy.__file__)
    assert spec is not None and spec.loader is not None
    imported = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as patch:
        patch.setattr(logging, "getLogger", forbidden)
        patch.setattr(metadata, "version", forbidden)
        spec.loader.exec_module(imported)
    assert imported._configured is False


def test_startup_is_explicit_idempotent_and_changes_only_manifest_disabled_flags() -> None:
    loggers = [logging.getLogger(name) for name in (*policy.CREDENTIAL_LOGGER_NAMES, "httpcore")]
    loggers += [logging.getLogger(), logging.getLogger("torii.identity")]
    for logger in loggers:
        logger.disabled = False
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        logger.handlers[:] = [logging.NullHandler()]
    before = [(logger, logger.level, logger.propagate, logger.handlers[:]) for logger in loggers]
    global_disable = logging.root.manager.disable

    policy.configure_credential_logging()
    policy.configure_credential_logging()
    policy.assert_credential_logging()

    assert policy._configured is True
    assert set(policy.CREDENTIAL_LOGGER_NAMES) == _EXPECTED_LOGGERS
    assert dict(policy.CREDENTIAL_PACKAGE_VERSIONS) == _EXPECTED_VERSIONS
    for logger, level, propagate, handlers in before:
        assert logger.disabled is (logger.name in _EXPECTED_LOGGERS)
        assert (logger.level, logger.propagate, logger.handlers) == (level, propagate, handlers)
    assert logging.root.manager.disable == global_disable


def test_disabled_emitters_without_explicit_startup_do_not_authorize_requests() -> None:
    for name in policy.CREDENTIAL_LOGGER_NAMES:
        logging.getLogger(name).disabled = True
    with pytest.raises(DomainError) as caught:
        policy.assert_credential_logging()
    _assert_safe_failure(caught.value)


@pytest.mark.parametrize("name", sorted(_EXPECTED_LOGGERS))
def test_guard_detects_each_reenabled_emitter_without_repairing_it(name: str) -> None:
    policy.configure_credential_logging()
    logger = logging.getLogger(name)
    logger.disabled = False

    with pytest.raises(DomainError) as caught:
        policy.assert_credential_logging()

    _assert_safe_failure(caught.value)
    assert logger.disabled is False


@pytest.mark.parametrize("package", sorted(_EXPECTED_VERSIONS))
@pytest.mark.parametrize("failure", ["changed", "missing", "unexpected"])
def test_bad_package_metadata_refuses_startup_and_invalidates_previous_success(
    monkeypatch: pytest.MonkeyPatch, package: str, failure: str
) -> None:
    policy.configure_credential_logging()
    for name in policy.CREDENTIAL_LOGGER_NAMES:
        logging.getLogger(name).disabled = False

    def version(name: str) -> str:
        if name != package:
            return _EXPECTED_VERSIONS[name]
        if failure == "missing":
            raise metadata.PackageNotFoundError(_MARKER)
        if failure == "unexpected":
            raise RuntimeError(_MARKER)
        return "999.0.0"

    monkeypatch.setattr(metadata, "version", version)
    with pytest.raises(DomainError) as caught:
        policy.configure_credential_logging()
    _assert_safe_failure(caught.value)
    assert policy._configured is False
    assert all(logging.getLogger(name).disabled is False for name in _EXPECTED_LOGGERS)
    with pytest.raises(DomainError) as caught:
        policy.assert_credential_logging()
    _assert_safe_failure(caught.value)


@pytest.mark.parametrize("operation", ["configure", "assert"])
def test_logging_lookup_failure_is_safe(monkeypatch: pytest.MonkeyPatch, operation: str) -> None:
    policy.configure_credential_logging()

    def failed_lookup(name: str) -> logging.Logger:
        raise RuntimeError(_MARKER)

    # Keep pytest's own logging functional while exercising our module's lookup.
    class BrokenLogging:
        getLogger = staticmethod(failed_lookup)

    monkeypatch.setattr(policy, "logging", BrokenLogging)
    function = (
        policy.configure_credential_logging
        if operation == "configure"
        else policy.assert_credential_logging
    )
    with pytest.raises(DomainError) as caught:
        function()
    _assert_safe_failure(caught.value)


class _Records(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def test_direct_and_root_handlers_cannot_observe_credentials_while_torii_still_logs() -> None:
    root = logging.getLogger()
    root.disabled = False
    root.setLevel(logging.DEBUG)
    root_capture = _Records()
    root.addHandler(root_capture)
    captures: list[_Records] = []
    for name in _EXPECTED_LOGGERS:
        logger = logging.getLogger(name)
        logger.disabled = False
        logger.setLevel(logging.DEBUG)
        logger.propagate = True
        capture = _Records()
        captures.append(capture)
        logger.addHandler(capture)
    torii = logging.getLogger("torii.identity")
    torii.disabled = False
    torii.setLevel(logging.INFO)
    torii.handlers[:] = []
    torii.propagate = True
    logging.disable(logging.NOTSET)
    policy.configure_credential_logging()

    for name in _EXPECTED_LOGGERS:
        for level in (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR):
            logging.getLogger(name).log(level, "Authorization/body/reason/exception=%s", _MARKER)
    # Exercise the pinned library's own formatting path, which can include
    # headers, return values and exceptions when DEBUG is enabled.
    for name in _EXPECTED_LOGGERS - {"httpx"}:
        with (
            pytest.raises(RuntimeError, match=_MARKER),
            Trace("request", logging.getLogger(name), kwargs={"headers": _MARKER}),
        ):
            raise RuntimeError(_MARKER)
    torii.info("safe Torii event")
    root.info("safe root event")

    assert all(capture.messages == [] for capture in captures)
    assert root_capture.messages == ["safe Torii event", "safe root event"]


def _literal_logger_names(source: str) -> set[str]:
    """Recognize the pinned packages' constructors; require review for new forms."""
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "logging" and isinstance(node.ctx, ast.Load):
            parent = parents.get(node)
            if not isinstance(parent, ast.Attribute) or parent.attr not in {
                "getLogger",
                "Logger",
                "DEBUG",
            }:
                raise AssertionError("Unreviewed logging namespace use")
        # Treat aliases/references to constructors as unknown too: silently
        # skipping `factory = logging.getLogger; factory(name)` defeats the gate.
        if isinstance(node, ast.Attribute) and node.attr in {"getLogger", "getChild", "Logger"}:
            parent = parents.get(node)
            if (
                node.attr == "Logger"
                and isinstance(parent, ast.arg)
                and parent.annotation is node
                and isinstance(node.value, ast.Name)
                and node.value.id == "logging"
            ):
                continue  # HTTPCore's Trace logger parameter is a type annotation.
            if (
                node.attr != "getLogger"
                or not isinstance(node.value, ast.Name)
                or node.value.id != "logging"
                or not isinstance(parent, ast.Call)
                or parent.func is not node
            ):
                raise AssertionError("Unreviewed logging constructor or alias")
            call = parent
            if (
                len(call.args) != 1
                or call.keywords
                or not isinstance(call.args[0], ast.Constant)
                or type(call.args[0].value) is not str
            ):
                raise AssertionError("Unreviewed dynamic logger name")
            names.add(call.args[0].value)
        if isinstance(node, ast.ImportFrom) and node.module == "logging":
            raise AssertionError("Unreviewed logging import alias")
        if isinstance(node, ast.Import) and any(
            alias.name == "logging" and alias.asname is not None for alias in node.names
        ):
            raise AssertionError("Unreviewed logging module alias")
    return names


def test_installed_pinned_package_sources_match_reviewed_emitter_manifest() -> None:
    assert {name: metadata.version(name) for name in _EXPECTED_VERSIONS} == _EXPECTED_VERSIONS
    names: set[str] = set()
    for package in (httpx, httpcore):
        assert package.__file__ is not None
        paths = list(Path(package.__file__).parent.rglob("*.py"))
        assert paths, "Source is required to review the dependency logger manifest"
        for path in paths:
            names.update(_literal_logger_names(path.read_text(encoding="utf-8")))
    assert names == set(policy.CREDENTIAL_LOGGER_NAMES) == _EXPECTED_LOGGERS


@pytest.mark.parametrize(
    "source",
    [
        "logging.getLogger(name)",
        "logging.getLogger()",
        "logging.getLogger(name='httpx')",
        "logging.getLogger('httpx', extra)",
        "logging.getLogger('httpx').getChild('new')",
        "logging.Logger('httpx')",
        "factory = logging.getLogger\nfactory('httpx')",
        "from logging import getLogger as factory\nfactory('httpx')",
        "import logging as log\nlog.getLogger('httpx')",
        "getattr(logging, 'getLogger')('httpx')",
        "logging.info('a new emission path')",
    ],
)
def test_manifest_scanner_rejects_unreviewed_logger_constructions(source: str) -> None:
    with pytest.raises(AssertionError, match="Unreviewed"):
        _literal_logger_names(source)


def test_manifest_scanner_exposes_new_literal_emitter_for_review() -> None:
    names = _literal_logger_names("logging.getLogger('httpx.future')")
    assert names - _EXPECTED_LOGGERS == {"httpx.future"}
