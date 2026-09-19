"""SPEC-0001 B2a3: emit our own safe error independently of caller handlers."""

from typing import Never

from torii_api.domain.errors import DomainError


def raise_identity_error(status: int = 503) -> Never:
    failure = (
        DomainError(401, "unauthorized")
        if status == 401
        else DomainError(503, "identity_unavailable")
    )
    try:
        raise failure from None
    finally:
        # Python attaches even an already-handled caller exception at raise time.
        # Clear only this new error, never mutate the caller/provider exception.
        # CPython may reattach an ambient caller exception after an async timeout;
        # from None still hides it. No provider exception is retained here.
        failure.__context__ = None
