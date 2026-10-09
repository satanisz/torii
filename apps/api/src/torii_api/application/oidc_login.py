"""SPEC-0001 B2a4c: internal OIDC orchestration, not HTTP authentication.

Whole synchronous store calls run off-loop and are always joined. Cancellation
does not claim to stop SQL/COMMIT; known late sessions receive one compensation.
No routes, cookies, permission grants, background jobs or bearer authentication.
"""

import asyncio
import base64
import logging
import math
import threading
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import cast
from urllib.parse import urlencode

import httpx
from sqlalchemy import Engine

from torii_api.application.identity_store import IdentityStore, NewSession
from torii_api.config import Settings
from torii_api.domain.errors import DomainError
from torii_api.security.credential_logging import assert_credential_logging
from torii_api.security.oidc_cache import OidcKeyCache
from torii_api.security.oidc_errors import raise_identity_error
from torii_api.security.oidc_exchange import OidcCredentialTransport
from torii_api.security.oidc_replies import TokenReply
from torii_api.security.oidc_requests import OAuthRequests
from torii_api.security.oidc_tokens import TokenVerifier, token_key_id
from torii_api.security.oidc_transport import OidcMetadataTransport, RealmEndpoints
from torii_api.security.session_secrets import SecretCodec, token_hash

_LOGGER = logging.getLogger("torii.identity")
_CLEANUP_PRIORITY = {
    "none": 0,
    "remote_failed": 1,
    "secret_corrupt": 2,
    "local_failed": 3,
    "commit_unknown": 4,
}


@dataclass(frozen=True, slots=True)
class LoginStart:
    authorization_url: str = field(repr=False)
    browser: str = field(repr=False)


@dataclass(slots=True, repr=False)
class _Operation:
    name: str
    started: float = field(default_factory=time.monotonic)
    deadline: float = 0.0
    outcome: str = "unavailable"
    cleanup: str = "none"
    cancelled: asyncio.CancelledError | None = None

    def note(self, cleanup: str) -> None:
        if _CLEANUP_PRIORITY[cleanup] > _CLEANUP_PRIORITY[self.cleanup]:
            self.cleanup = cleanup


@dataclass(slots=True, repr=False)
class _DatabaseResult[T]:
    value: T | None = None
    status: int = 200
    started: bool = False


def _status(error: DomainError) -> int:
    return 401 if error.status == 401 and error.code == "unauthorized" else 503


def _opaque(value: object, limit: int) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= limit
        and all(0x21 <= ord(char) <= 0x7E for char in value)
    )


def _work_deadline(deadline: float, now: float) -> float:
    if (
        type(deadline) not in (int, float)
        or not 0 <= deadline <= 2**53 - 1
        or not math.isfinite(deadline)
    ):
        raise_identity_error()
    work = min(float(deadline), now + 15.0) - 1.0
    if work <= now:
        raise_identity_error()
    return work


def _check(operation: _Operation) -> None:
    if operation.cancelled is not None:
        raise operation.cancelled
    if asyncio.get_running_loop().time() >= operation.deadline:
        raise_identity_error()


def _event(operation: _Operation) -> None:
    elapsed = time.monotonic() - operation.started
    duration = int(max(0.0, elapsed) * 1000) if math.isfinite(elapsed) else 0
    # An operator's logging handler cannot replace a committed result or
    # cancellation with its own exception/details.
    with suppress(Exception):
        _LOGGER.info(
            "oidc_login",
            extra={
                "event": "oidc_login",
                "operation": operation.name,
                "outcome": operation.outcome,
                "cleanup": operation.cleanup,
                "duration_ms": duration,
            },
        )


async def _join[T](future: asyncio.Future[T], operation: _Operation) -> T:
    """Only protect completion of owned work, remembering repeated cancellation."""
    while not future.done():
        try:
            await asyncio.shield(future)
        except asyncio.CancelledError as error:
            if operation.cancelled is None:
                operation.cancelled = error
    # All expected worker failures are represented as safe data, not exceptions.
    # Do not suppress BaseException from an unexpected terminating dependency.
    return future.result()


class OidcLoginService:
    def __init__(
        self,
        engine: Engine,
        settings: Settings,
        *,
        metadata_transport: httpx.AsyncBaseTransport | None = None,
        credential_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        try:
            self._endpoints = RealmEndpoints(settings.oidc_issuer, settings.oidc_backchannel_url)
            origin = self._endpoints.issuer.split("/identity/realms/", 1)[0]
            if settings.public_url != origin or any(
                value is not None and not isinstance(value, httpx.AsyncBaseTransport)
                for value in (metadata_transport, credential_transport)
            ):
                raise ValueError("invalid identity configuration")
            self._client_id = settings.oidc_client_id
            self._redirect = origin + "/auth/callback"
            self._verifier = TokenVerifier(
                self._endpoints.issuer, settings.oidc_client_id, settings.oidc_audience
            )
            self._store = IdentityStore(
                engine, SecretCodec(settings.session_key.encode("ascii")), self._endpoints.issuer
            )
            # Validate credentials before creating either client (pure A4a).
            OAuthRequests(self._endpoints, settings.oidc_client_id, settings.oidc_client_secret)
            self._metadata = OidcMetadataTransport(self._endpoints, transport=metadata_transport)
            self._credentials = OidcCredentialTransport(
                self._endpoints,
                settings.oidc_client_id,
                settings.oidc_client_secret,
                transport=credential_transport,
            )
            self._cache = OidcKeyCache(self._metadata)
            self._loop: asyncio.AbstractEventLoop | None = None
            self._closed = False
            self._active = 0
            self._idle = asyncio.Event()
            self._idle.set()
            self._db_slots = asyncio.Semaphore(4)
            self._workers: set[asyncio.Future[object]] = set()
            self._close_task: asyncio.Task[bool] | None = None
            return
        except Exception:
            # Construction never opens a socket; no partial service escapes.
            pass
        raise_identity_error()

    def __repr__(self) -> str:
        return "OidcLoginService()"

    def _bind_loop(self) -> asyncio.AbstractEventLoop:
        loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not loop:
            raise_identity_error()
        self._loop = loop
        return loop

    async def _run[T](
        self, name: str, deadline: float, action: Callable[[_Operation], Awaitable[T]]
    ) -> T:
        operation = _Operation(name)
        entered = False
        status = 503
        try:
            loop = self._bind_loop()
            if self._closed:
                raise_identity_error()
            operation.deadline = _work_deadline(deadline, loop.time())
            self._active += 1
            self._idle.clear()
            entered = True
            result = await action(operation)
            operation.outcome = "success"
            return result
        except asyncio.CancelledError:
            operation.outcome = "cancelled"
            raise
        except DomainError as error:
            status = _status(error)
            operation.outcome = "unauthorized" if status == 401 else "unavailable"
        except Exception:
            status = 503
        finally:
            if entered:
                self._active -= 1
                if self._active == 0:
                    self._idle.set()
            _event(operation)
        raise_identity_error(status)

    async def _db_call[T](
        self,
        operation: _Operation,
        function: Callable[[], T],
        *,
        compensate: bool = False,
        cleanup: bool = False,
    ) -> T:
        loop = asyncio.get_running_loop()
        if cleanup:
            # Cleanup is required even after the original deadline/cancel. Its
            # permit waiter is owned and joined, never a detached acquisition.
            await _join(asyncio.create_task(self._db_slots.acquire()), operation)
        else:
            _check(operation)
            async with asyncio.timeout_at(operation.deadline):
                await self._db_slots.acquire()
        stop = threading.Event()
        # Translate the loop's remaining duration, not its absolute epoch, to
        # the worker's clock. A queued executor job checks immediately before SQL.
        cutoff = time.monotonic() + max(0.0, operation.deadline - loop.time())

        def invoke() -> _DatabaseResult[T]:
            if not cleanup and (stop.is_set() or time.monotonic() >= cutoff):
                return _DatabaseResult(status=503)
            try:
                return _DatabaseResult(value=function(), started=True)
            except DomainError as error:
                return _DatabaseResult(status=_status(error), started=True)
            except Exception:
                return _DatabaseResult(status=503, started=True)

        future: asyncio.Future[_DatabaseResult[T]] | None = None
        expired = False
        try:
            if not cleanup:
                _check(operation)
            future = loop.run_in_executor(None, invoke)
            self._workers.add(cast(asyncio.Future[object], future))
            if not cleanup:
                try:
                    async with asyncio.timeout_at(operation.deadline):
                        await asyncio.shield(future)
                except TimeoutError:
                    expired = True
                    stop.set()
                except asyncio.CancelledError as error:
                    operation.cancelled = error
                    stop.set()
            outcome = await _join(future, operation)
        finally:
            # The joined Future is safe to release; no compensation may wait
            # for another permit while retaining this one (four-way deadlock).
            if future is not None:
                self._workers.discard(cast(asyncio.Future[object], future))
            self._db_slots.release()

        if outcome.started and outcome.status == 503:
            # Store exposes no execute-vs-COMMIT distinction. Conservative only.
            operation.note("commit_unknown")
        late = expired or loop.time() >= operation.deadline or operation.cancelled is not None
        if not cleanup and late:
            if compensate and isinstance(outcome.value, NewSession):
                await self._compensate(operation, outcome.value)
            _check(operation)
            raise_identity_error()
        if outcome.status != 200:
            raise_identity_error(outcome.status)
        return cast(T, outcome.value)

    async def _compensate(self, operation: _Operation, session: NewSession) -> None:
        try:
            await self._db_call(
                operation, lambda: self._store.revoke_session(session.session_id), cleanup=True
            )
        except DomainError as error:
            if error.status != 401:
                operation.note("local_failed")
        except Exception:
            operation.note("local_failed")

    async def _revoke_refresh(self, operation: _Operation, refresh: str | None) -> None:
        if (
            refresh is None
            or operation.cancelled is not None
            or asyncio.get_running_loop().time() >= operation.deadline
        ):
            return
        try:
            await self._credentials.revoke(refresh, deadline=operation.deadline)
        except Exception:
            operation.note("remote_failed")

    async def start(self, *, deadline: float) -> LoginStart:
        return await self._run("start", deadline, self._start)

    async def _start(self, operation: _Operation) -> LoginStart:
        assert_credential_logging()
        flow = await self._db_call(operation, self._store.create_flow)
        challenge = base64.urlsafe_b64encode(bytes.fromhex(token_hash(flow.verifier)))
        query = urlencode(
            [
                ("client_id", self._client_id),
                ("redirect_uri", self._redirect),
                ("response_type", "code"),
                ("scope", "openid profile"),
                ("state", flow.state),
                ("nonce", flow.nonce),
                ("code_challenge", challenge.rstrip(b"=").decode("ascii")),
                ("code_challenge_method", "S256"),
            ]
        )
        result = LoginStart(
            self._endpoints.issuer + "/protocol/openid-connect/auth?" + query, flow.browser
        )
        _check(operation)
        return result

    async def callback(
        self,
        state: str,
        browser: str,
        *,
        code: str | None = None,
        error: str | None = None,
        previous_session: str | None = None,
        deadline: float,
    ) -> NewSession:
        return await self._run(
            "callback",
            deadline,
            lambda operation: self._callback(
                operation, state, browser, code, error, previous_session
            ),
        )

    async def _callback(
        self,
        operation: _Operation,
        state: str,
        browser: str,
        code: str | None,
        error: str | None,
        previous_session: str | None,
    ) -> NewSession:
        assert_credential_logging()
        if (code is None) == (error is None) or (
            (code is not None and not _opaque(code, 4096))
            or (error is not None and not _opaque(error, 256))
        ):
            raise_identity_error(401)
        consumed = await self._db_call(operation, lambda: self._store.consume_flow(state, browser))
        if code is None:
            raise_identity_error(401)
        reply: TokenReply | None = None
        status = 503
        try:
            _check(operation)
            reply = await self._credentials.exchange(
                code, consumed.verifier, deadline=operation.deadline
            )
            if type(reply) is not TokenReply:
                reply = None
                raise_identity_error()
            _check(operation)
            kids = (token_key_id(reply.id_token), token_key_id(reply.access_token))
            keys = await self._cache.keys_for(kids, deadline=operation.deadline)
            _check(operation)
            identity = self._verifier.verify_login(
                reply.id_token, reply.access_token, consumed.nonce_hash, keys
            )
            _check(operation)
            refresh = reply.refresh_token
            return await self._db_call(
                operation,
                lambda: self._store.create_session(identity, previous_session, refresh),
                compensate=True,
            )
        except DomainError as failure:
            status = _status(failure)
        except Exception:
            status = 503
        # Exit the original handler before awaiting cleanup: a cancellation
        # during revoke must not inherit a provider exception as its context.
        # CancelledError bypasses both handlers and never starts remote revoke.
        if reply is not None:
            await self._revoke_refresh(operation, reply.refresh_token)
        raise_identity_error(status)

    async def logout(self, session_id: str, *, deadline: float) -> None:
        await self._run("logout", deadline, lambda operation: self._logout(operation, session_id))

    async def _logout(self, operation: _Operation, session_id: str) -> None:
        # Local revocation must remain possible when credential logging/IdP fails.
        revoked = await self._db_call(operation, lambda: self._store.revoke_session(session_id))
        if revoked.secret_error:
            operation.note("secret_corrupt")
        await self._revoke_refresh(operation, revoked.refresh_token)

    async def _close(self) -> bool:
        await self._idle.wait()
        success = True
        cancelled: asyncio.CancelledError | None = None
        for client in (self._metadata, self._credentials):
            try:
                async with asyncio.timeout(1.0):
                    await client.aclose()
            except asyncio.CancelledError as error:
                # Even a dependency that cancels itself must not skip cleanup
                # of the other owned client. Callers still observe cancellation.
                if cancelled is None:
                    cancelled = error
            except Exception:
                success = False
        if cancelled is not None:
            raise cancelled
        return success

    async def aclose(self) -> None:
        operation = _Operation("close")
        success = False
        try:
            self._bind_loop()
            self._closed = True
            if self._close_task is None:
                self._close_task = asyncio.create_task(self._close())
            success = await _join(self._close_task, operation)
            if operation.cancelled is not None:
                raise operation.cancelled
            operation.outcome = "success" if success else "unavailable"
        except asyncio.CancelledError:
            operation.outcome = "cancelled"
            raise
        except Exception:
            success = False
        finally:
            _event(operation)
        if not success:
            raise_identity_error()
