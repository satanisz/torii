"""SPEC-0001 B2a4b / A4b-05: explicit process policy for credential transports.

HTTPX and HTTPCore share these emitters across clients. Disable them once at
startup, including handlers attached directly to an emitter, without changing
other application logging. Importing this module does not configure logging.
"""

import logging
from importlib import metadata
from typing import Final

from torii_api.security.oidc_errors import raise_identity_error

CREDENTIAL_LOGGER_NAMES: Final[tuple[str, ...]] = (
    "httpx",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
    "httpcore.socks",
)
CREDENTIAL_PACKAGE_VERSIONS: Final[tuple[tuple[str, str], ...]] = (
    ("httpx", "0.28.1"),
    ("httpcore", "1.0.9"),
)

_configured = False


def configure_credential_logging() -> None:
    """Install the reviewed policy explicitly; never restore it at client close."""
    global _configured
    # A failed subsequent startup must not retain an earlier successful state.
    _configured = False
    active = False
    try:
        if all(metadata.version(package) == pin for package, pin in CREDENTIAL_PACKAGE_VERSIONS):
            for name in CREDENTIAL_LOGGER_NAMES:
                logging.getLogger(name).disabled = True
            active = _emitters_disabled()
    except Exception:
        # Metadata/configuration failures may contain local or injected details.
        # Raise our own error outside the handler, without retaining that error.
        pass
    if not active:
        raise_identity_error()
    _configured = True


def assert_credential_logging() -> None:
    """Refuse credential I/O unless startup policy still holds; never repair it."""
    active = False
    if _configured:
        try:
            active = _emitters_disabled()
        except Exception:
            active = False
    if not active:
        raise_identity_error()


def _emitters_disabled() -> bool:
    return all(logging.getLogger(name).disabled is True for name in CREDENTIAL_LOGGER_NAMES)
