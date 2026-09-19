"""SPEC-0001 B2a3 A3-03/04: one-loop bounded metadata/key snapshots, no auth.

Callers must still verify signatures and claims with TokenVerifier. A key hint
does not authenticate anyone. This cache performs no DB writes or HTTP routing.
"""

import asyncio
import math
from typing import TYPE_CHECKING

from torii_api.security.oidc_errors import raise_identity_error
from torii_api.security.oidc_keys import SigningKeys, valid_kid

if TYPE_CHECKING:
    from torii_api.security.oidc_transport import OidcMetadataTransport

_TTL = 300.0
_COOLDOWN = 30.0


def _check_deadline(deadline: float, now: float) -> None:
    if (
        type(deadline) not in (int, float)
        or not 0 <= deadline <= 2**53 - 1
        or not math.isfinite(deadline)
        or deadline <= now
    ):
        raise_identity_error()


class OidcKeyCache:
    """One issuer/process/event-loop, O(1) state and no detached refresh task."""

    def __init__(self, transport: "OidcMetadataTransport") -> None:
        self._transport = transport
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._keys: SigningKeys | None = None
        self._keys_until = 0.0
        self._discovery_until = 0.0
        self._retry_at = 0.0
        self._last_refresh_ok = False

    def _known(self, kids: tuple[str, ...], now: float) -> SigningKeys | None:
        keys = self._keys
        if (
            keys is not None
            and now < self._keys_until
            and all(keys.key_for(kid) is not None for kid in kids)
        ):
            return keys
        return None

    async def _lookup(
        self, kids: tuple[str, ...], deadline: float, loop: asyncio.AbstractEventLoop
    ) -> tuple[SigningKeys | None, int]:
        known = self._known(kids, loop.time())
        if known is not None:
            return known, 200
        # The caller's timeout includes lock acquisition, not only network I/O.
        async with self._lock:
            now = loop.time()
            _check_deadline(deadline, now)
            known = self._known(kids, now)
            if known is not None:
                return known, 200
            if now < self._retry_at:
                # After a failed/cancelled attempt, absence cannot be treated as
                # evidence of an invalid credential, even with an older snapshot.
                successful_fresh = self._last_refresh_ok and now < self._keys_until
                return None, 401 if successful_fresh else 503
            self._retry_at = now + _COOLDOWN
            self._last_refresh_ok = False
            if now >= self._discovery_until:
                await self._transport.discovery(deadline=deadline)
                now = loop.time()
                _check_deadline(deadline, now)
                self._discovery_until = now + _TTL
            keys = await self._transport.jwks(deadline=deadline)
            now = loop.time()
            _check_deadline(deadline, now)
            if not isinstance(keys, SigningKeys):
                raise_identity_error()
            # Publish only a fully validated immutable snapshot. Never merge.
            self._keys = keys
            self._keys_until = now + _TTL
            self._last_refresh_ok = True
            return self._known(kids, now), 401

    async def keys_for(self, kids: tuple[str, ...], *, deadline: float) -> SigningKeys:
        if type(kids) is not tuple or not 1 <= len(kids) <= 2 or not all(map(valid_kid, kids)):
            raise_identity_error(401)
        loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not loop:
            raise_identity_error()
        self._loop = loop
        status = 503
        try:
            _check_deadline(deadline, loop.time())
            async with asyncio.timeout_at(deadline):
                keys, status = await self._lookup(kids, deadline, loop)
                _check_deadline(deadline, loop.time())
            if keys is not None:
                return keys
        except Exception:
            # This dependency boundary deliberately drops provider details and
            # exception context. BaseException/CancelledError still propagates.
            status = 503
        raise_identity_error(status)
