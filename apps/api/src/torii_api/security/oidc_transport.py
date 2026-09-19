"""SPEC-0001 B2a3 A3-01/02: trusted fixed endpoints and bounded metadata GET.

Network trust/DNS are deployment responsibilities. This is not a generic URL
fetcher and is not yet connected to any request, login or credential exchange.
"""

import asyncio
import math
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from http.cookiejar import CookieJar, DefaultCookiePolicy

import httpx

from torii_api.domain.errors import DomainError
from torii_api.security.oidc_errors import raise_identity_error
from torii_api.security.oidc_keys import SigningKeys, decode_object

_URL = re.compile(
    r"(?P<scheme>https?)://(?P<host>[a-z0-9.-]+)"
    r"(?::(?P<port>[1-9][0-9]{0,4}))?"
    r"(?P<path>/identity/realms/[A-Za-z0-9_-]{1,128})"
)
_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_CONTENT_TYPE = re.compile(
    r"[ \t]*application/(?:json|jwk-set\+json)[ \t]*"
    r'(?:;[ \t]*charset[ \t]*=[ \t]*(?:utf-8|"utf-8")[ \t]*)?',
    re.IGNORECASE | re.ASCII,
)
_DECIMAL = re.compile(r"[0-9]+")
_OIDC = "/protocol/openid-connect/"
_MAX_BODY = 65536
_SAFE_ERRORS = (
    httpx.HTTPError,
    httpx.InvalidURL,
    DomainError,
    ValueError,
    TypeError,
    OSError,
    RuntimeError,
)


class _BoundedCloseStream(httpx.AsyncByteStream):
    """Bound even HTTPX's own automatic/error-path cleanup, not only our finally."""

    def __init__(self, stream: httpx.AsyncByteStream) -> None:
        self._stream = stream

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._stream:
            yield chunk

    async def aclose(self) -> None:
        async with asyncio.timeout(1.0):
            await self._stream.aclose()


async def _bound_response_close(response: httpx.Response) -> None:
    # Response hooks run before HTTPX parses Location, even with redirects off.
    if not isinstance(response.stream, httpx.AsyncByteStream):
        raise ValueError("invalid metadata stream")
    response.stream = _BoundedCloseStream(response.stream)


def _realm_path(value: str, *, public: bool) -> str:
    if type(value) is not str or not 1 <= len(value) <= 2048:
        raise_identity_error()
    match = _URL.fullmatch(value)
    if match is None:
        raise_identity_error()
    host, scheme, port = match.group("host", "scheme", "port")
    if (
        any(_DNS_LABEL.fullmatch(label) is None for label in host.split("."))
        or (port is not None and int(port) > 65535)
        or (scheme != "https" and (public or host != "identity"))
    ):
        raise_identity_error()
    return match.group("path")


@dataclass(frozen=True, slots=True)
class RealmEndpoints:
    """Server-configured URLs; never values derived from discovery or a JWT."""

    issuer: str = field(repr=False)
    backchannel: str = field(repr=False)

    def __post_init__(self) -> None:
        if _realm_path(self.issuer, public=True) != _realm_path(self.backchannel, public=False):
            raise_identity_error()

    @property
    def discovery_url(self) -> str:
        return self.backchannel + "/.well-known/openid-configuration"

    @property
    def jwks_url(self) -> str:
        return self.backchannel + _OIDC + "certs"

    def validate_discovery(self, data: bytes) -> None:
        try:
            value = decode_object(data, limit=_MAX_BODY)
            if (
                value.get("issuer") != self.issuer
                or value.get("authorization_endpoint") != self.issuer + _OIDC + "auth"
            ):
                raise ValueError("invalid discovery")
            for field_name, suffix in (
                ("token_endpoint", "token"),
                ("jwks_uri", "certs"),
                ("revocation_endpoint", "revoke"),
            ):
                endpoint = value.get(field_name)
                if type(endpoint) is not str or endpoint not in (
                    self.issuer + _OIDC + suffix,
                    self.backchannel + _OIDC + suffix,
                ):
                    raise ValueError("invalid discovery")
            return
        except (ValueError, TypeError):
            pass
        raise_identity_error()


def _check_headers(response: httpx.Response) -> None:
    if response.status_code != 200:
        raise ValueError("invalid metadata response")
    types = response.headers.get_list("content-type")
    encodings = response.headers.get_list("content-encoding")
    lengths = response.headers.get_list("content-length")
    if (
        len(types) != 1
        or _CONTENT_TYPE.fullmatch(types[0]) is None
        or (encodings and (len(encodings) != 1 or encodings[0].lower() != "identity"))
        or len(lengths) > 1
    ):
        raise ValueError("invalid metadata response")
    if lengths:
        length = lengths[0]
        if _DECIMAL.fullmatch(length) is None:
            raise ValueError("invalid metadata response")
        # Ignore leading zeroes for numeric comparison, without unbounded int conversion.
        significant = length.lstrip("0") or "0"
        if len(significant) > 5 or int(significant) > _MAX_BODY:
            raise ValueError("invalid metadata response")


def _operation_deadline(deadline: float) -> float:
    if (
        type(deadline) not in (int, float)
        or not 0 <= deadline <= 2**53 - 1
        or not math.isfinite(deadline)
    ):
        raise_identity_error()
    now = asyncio.get_running_loop().time()
    if deadline <= now:
        raise_identity_error()
    return min(float(deadline), now + 5.0)


def _check_time(deadline: float) -> None:
    if asyncio.get_running_loop().time() >= deadline:
        raise_identity_error()


class OidcMetadataTransport:
    """Dedicated stateless client; callers own its explicit async lifecycle."""

    __slots__ = ("_client", "_closed", "_endpoints")

    def __init__(
        self, endpoints: RealmEndpoints, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        if type(endpoints) is not RealmEndpoints or (
            transport is not None and not isinstance(transport, httpx.AsyncBaseTransport)
        ):
            raise_identity_error()
        try:
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
        except _SAFE_ERRORS:
            pass
        raise_identity_error()

    def __repr__(self) -> str:
        return "OidcMetadataTransport()"

    @property
    def endpoints(self) -> RealmEndpoints:
        return self._endpoints

    async def _get(self, url: str) -> bytes:
        request = httpx.Request(
            "GET", url, headers={"Accept": "application/json", "Accept-Encoding": "identity"}
        )
        response = await self._client.send(request, stream=True, auth=None, follow_redirects=False)
        cancelled = False
        try:
            _check_headers(response)
            body = bytearray()
            async for chunk in response.aiter_raw():
                if len(body) + len(chunk) > _MAX_BODY:
                    raise ValueError("invalid metadata response")
                body.extend(chunk)
            return bytes(body)
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            try:
                await response.aclose()
            except Exception:
                # A secondary cleanup failure cannot replace caller cancellation.
                if not cancelled:
                    raise

    async def _load[T](self, url: str, parser: Callable[[bytes], T], *, deadline: float) -> T:
        if self._closed:
            raise_identity_error()
        cutoff = _operation_deadline(deadline)
        try:
            async with asyncio.timeout_at(cutoff):
                body = await self._get(url)
                _check_time(cutoff)
                result = parser(body)
                _check_time(cutoff)
                return result
        except _SAFE_ERRORS:
            pass
        # Outside handlers to avoid retaining URLs/body via __context__ or cause.
        raise_identity_error()

    async def discovery(self, *, deadline: float) -> None:
        await self._load(
            self._endpoints.discovery_url, self._endpoints.validate_discovery, deadline=deadline
        )

    async def jwks(self, *, deadline: float) -> SigningKeys:
        return await self._load(
            self._endpoints.jwks_url,
            lambda body: SigningKeys.from_jwks(body, issuer=self._endpoints.issuer),
            deadline=deadline,
        )

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            async with asyncio.timeout(1.0):
                await self._client.aclose()
            return
        except _SAFE_ERRORS:
            pass
        raise_identity_error()
