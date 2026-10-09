"""SPEC-0001 B2a4b: fixed credential POST, bounded lifecycle and safe diagnostics.

The returned TokenReply is untrusted. This module does not authenticate a user,
consume a flow, validate JWTs, create sessions, or retry requests.
"""

import asyncio
import base64
import logging
import math
import re
import time
from http.cookiejar import CookieJar, DefaultCookiePolicy

import httpx

from torii_api.domain.errors import DomainError
from torii_api.security.credential_logging import assert_credential_logging
from torii_api.security.oidc_errors import raise_identity_error
from torii_api.security.oidc_replies import TokenReply, validate_revocation_response
from torii_api.security.oidc_requests import OAuthRequest, OAuthRequests
from torii_api.security.oidc_transport import (
    RealmEndpoints,
    _bound_response_close,
    _check_time,
    _operation_deadline,
)

_MAX_BODY = 65536
_JSON_TYPE = re.compile(
    r"[ \t]*application/json[ \t]*"
    r'(?:;[ \t]*charset[ \t]*=[ \t]*(?:utf-8|"utf-8")[ \t]*)?',
    re.IGNORECASE | re.ASCII,
)
_DECIMAL = re.compile(r"[0-9]+")
_LOGGER = logging.getLogger("torii.identity")


def _validate_request(endpoints: RealmEndpoints, operation: str, request: OAuthRequest) -> None:
    if type(operation) is not str or operation not in ("exchange", "revoke"):
        raise ValueError("invalid operation")
    suffix = "token" if operation == "exchange" else "revoke"
    if (
        type(request) is not OAuthRequest
        or type(request.url) is not str
        or request.url != endpoints.backchannel + "/protocol/openid-connect/" + suffix
        or type(request.authorization) is not str
        or not request.authorization.startswith("Basic ")
        or len(request.authorization) > _MAX_BODY
        or type(request.body) is not bytes
        or not 1 <= len(request.body) <= _MAX_BODY
        or any(not 0x21 <= byte <= 0x7E for byte in request.body)
    ):
        raise ValueError("invalid credential request")
    encoded = request.authorization[6:].encode("ascii")
    decoded = base64.b64decode(encoded, validate=True)
    if base64.b64encode(decoded) != encoded or decoded.decode("ascii").count(":") != 1:
        raise ValueError("invalid credential request")


def _response_length(response: httpx.Response, operation: str) -> int | None:
    if response.status_code not in ((200, 400) if operation == "exchange" else (200,)):
        raise ValueError("invalid credential response")
    types = response.headers.get_list("content-type")
    encodings = response.headers.get_list("content-encoding")
    lengths = response.headers.get_list("content-length")
    if (encodings and (len(encodings) != 1 or encodings[0].lower() != "identity")) or len(
        lengths
    ) > 1:
        raise ValueError("invalid credential response")
    if operation == "exchange":
        if len(types) != 1 or _JSON_TYPE.fullmatch(types[0]) is None:
            raise ValueError("invalid credential response")
    elif types and (
        len(types) != 1 or len(types[0]) > 256 or any(not 0x20 <= ord(c) <= 0x7E for c in types[0])
    ):
        raise ValueError("invalid credential response")
    if not lengths:
        return None
    length = lengths[0]
    if _DECIMAL.fullmatch(length) is None:
        raise ValueError("invalid credential response")
    significant = length.lstrip("0") or "0"
    if len(significant) > 5 or int(significant) > _MAX_BODY:
        raise ValueError("invalid credential response")
    return int(significant)


def _event(operation: str, outcome: str, started: float) -> None:
    elapsed = time.monotonic() - started
    duration = int(max(0.0, elapsed) * 1000) if math.isfinite(elapsed) else 0
    _LOGGER.info(
        "oidc_transport",
        extra={
            "event": "oidc_transport",
            "operation": operation,
            "outcome": outcome,
            "duration_ms": duration,
        },
    )


class OidcCredentialTransport:
    """Dedicated client with explicit async ownership; no ambient auth or hooks."""

    __slots__ = ("_client", "_closed", "_endpoints", "_requests")

    def __init__(
        self,
        endpoints: RealmEndpoints,
        client_id: str,
        client_secret: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        try:
            if transport is not None and not isinstance(transport, httpx.AsyncBaseTransport):
                raise ValueError("invalid transport")
            self._requests = OAuthRequests(endpoints, client_id, client_secret)
            self._client = httpx.AsyncClient(
                transport=transport,
                auth=None,
                cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])),
                trust_env=False,
                verify=True,
                follow_redirects=False,
                event_hooks={"response": [_bound_response_close]},
                limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
                timeout=httpx.Timeout(connect=2.0, pool=2.0, read=5.0, write=5.0),
            )
            self._endpoints = endpoints
            self._closed = False
            return
        except Exception:
            pass
        raise_identity_error()

    def __repr__(self) -> str:
        return "OidcCredentialTransport()"

    async def _post(
        self, operation: str, request: OAuthRequest, *, deadline: float
    ) -> TokenReply | None:
        if self._closed:
            raise_identity_error()
        cutoff = _operation_deadline(deadline)
        response: httpx.Response | None = None
        result: TokenReply | None = None
        status = 503
        completed = False
        cancelled = False
        try:
            async with asyncio.timeout_at(cutoff):
                _validate_request(self._endpoints, operation, request)
                outgoing = httpx.Request(
                    "POST",
                    request.url,
                    content=request.body,
                    headers={
                        "Authorization": request.authorization,
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                )
                assert_credential_logging()
                _check_time(cutoff)
                # No await between the guard and entry into send; no external trace extension.
                response = await self._client.send(
                    outgoing, stream=True, auth=None, follow_redirects=False
                )
                expected_length = _response_length(response, operation)
                body = bytearray()
                async for chunk in response.aiter_raw():
                    if len(body) + len(chunk) > _MAX_BODY:
                        raise ValueError("invalid credential response")
                    body.extend(chunk)
                if expected_length is not None and expected_length != len(body):
                    raise ValueError("invalid credential response")
                _check_time(cutoff)
                if operation == "exchange":
                    # Only this trusted parser is allowed to classify provider data as 401.
                    # A DomainError raised by the I/O stream or cleanup is handled below as 503.
                    try:
                        result = TokenReply.from_response(response.status_code, bytes(body))
                        completed = True
                    except DomainError as failure:
                        status = 401 if failure.status == 401 else 503
                else:
                    validate_revocation_response(response.status_code, bytes(body))
                    completed = True
                _check_time(cutoff)
        except asyncio.CancelledError:
            cancelled = True
            raise
        except Exception:
            completed = False
            status = 503
        finally:
            if response is not None:
                try:
                    # Outside the work budget: future orchestration reserves this final second.
                    # The A3 response hook also bounds HTTPX's internal cleanup before send returns.
                    async with asyncio.timeout(1.0):
                        await response.aclose()
                except Exception:
                    if not cancelled:
                        completed = False
                        status = 503
        if completed:
            return result
        # Outside all provider handlers: no credentials/response retained as exception context.
        raise_identity_error(status)

    async def exchange(self, code: str, verifier: str, *, deadline: float) -> TokenReply:
        started = time.monotonic()
        outcome = "unavailable"
        try:
            assert_credential_logging()
            if self._closed:
                raise_identity_error()
            request = self._requests.exchange(code, verifier)
            reply = await self._post("exchange", request, deadline=deadline)
            if type(reply) is not TokenReply:
                raise_identity_error()
            outcome = "success"
            return reply
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except DomainError as failure:
            outcome = "unauthorized" if failure.status == 401 else "unavailable"
            raise
        finally:
            _event("exchange", outcome, started)

    async def revoke(self, refresh_token: str, *, deadline: float) -> None:
        started = time.monotonic()
        outcome = "unavailable"
        try:
            assert_credential_logging()
            if self._closed:
                raise_identity_error()
            request = self._requests.revoke(refresh_token)
            await self._post("revoke", request, deadline=deadline)
            outcome = "success"
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        finally:
            _event("revoke", outcome, started)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            async with asyncio.timeout(1.0):
                await self._client.aclose()
            return
        except Exception:
            pass
        raise_identity_error()
