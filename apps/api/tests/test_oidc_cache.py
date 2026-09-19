"""SPEC-0001 B2a3 A3-03/04: monotonic snapshots and bounded refresh concurrency."""

import asyncio
import json
import traceback

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from torii_api.domain.errors import DomainError
from torii_api.security.oidc_cache import OidcKeyCache
from torii_api.security.oidc_keys import SigningKeys

ISSUER = "https://synthetic.example.invalid/identity/realms/test"
MARKER = "synthetic-secret-do-not-expose"


@pytest.fixture(scope="module")
def snapshots():
    def make(*kids):
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
        keys = [public | {"kid": kid} for kid in kids]
        return SigningKeys.from_jwks(json.dumps({"keys": keys}).encode(), issuer=ISSUER)

    return make("old"), make("new"), make("old"), make("old", "new")


class Source:
    def __init__(self, keys):
        self.keys = keys
        self.calls = []
        self.failure = None
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()

    async def discovery(self, *, deadline):
        self.calls.append("discovery")
        if self.failure == "discovery":
            raise ValueError(MARKER)

    async def jwks(self, *, deadline):
        self.calls.append("jwks")
        self.entered.set()
        await self.release.wait()
        if self.failure == "jwks":
            raise DomainError(503, MARKER)
        return self.keys


class Clock:
    def __init__(self, monkeypatch):
        self.loop = asyncio.get_running_loop()
        self.original = self.loop.time
        self.offset = 0
        monkeypatch.setattr(self.loop, "time", self.now)

    def now(self):
        return self.original() + self.offset

    def deadline(self):
        return self.now() + 15


async def error(status, operation):
    with pytest.raises(DomainError) as caught:
        await operation
    value = caught.value
    assert (value.status, value.code) == (
        status,
        "unauthorized" if status == 401 else "identity_unavailable",
    )
    assert value.__cause__ is value.__context__ is None
    assert MARKER not in "".join(traceback.format_exception(value))


def test_cold_cache_fast_path_and_two_kid_atomicity(snapshots):
    async def run():
        source = Source(snapshots[0])
        cache = OidcKeyCache(source)
        deadline = asyncio.get_running_loop().time() + 15
        assert await cache.keys_for(("old",), deadline=deadline) is snapshots[0]
        assert await cache.keys_for(("old", "old"), deadline=deadline) is snapshots[0]
        await error(401, cache.keys_for(("old", "new"), deadline=deadline))
        assert source.calls == ["discovery", "jwks"]
        assert MARKER not in repr(cache)

    asyncio.run(run())


def test_rotation_replaces_set_and_same_kid_material(snapshots, monkeypatch):
    async def run():
        clock = Clock(monkeypatch)
        source = Source(snapshots[0])
        cache = OidcKeyCache(source)
        old = await cache.keys_for(("old",), deadline=clock.deadline())
        source.keys = snapshots[1]
        clock.offset += 31
        new = await cache.keys_for(("new",), deadline=clock.deadline())
        assert new is snapshots[1]
        assert new.key_for("old") is None
        assert old.key_for("old") is not None  # already returned immutable snapshot
        await error(401, cache.keys_for(("old",), deadline=clock.deadline()))
        source.keys = snapshots[2]
        clock.offset += 31
        replaced = await cache.keys_for(("old",), deadline=clock.deadline())
        assert replaced.key_for("old") is not old.key_for("old")
        assert source.calls == ["discovery", "jwks", "jwks", "jwks"]

    asyncio.run(run())


def test_expiry_requires_new_discovery_and_jwks(snapshots, monkeypatch):
    async def run():
        clock = Clock(monkeypatch)
        source = Source(snapshots[0])
        cache = OidcKeyCache(source)
        await cache.keys_for(("old",), deadline=clock.deadline())
        clock.offset += 299
        await cache.keys_for(("old",), deadline=clock.deadline())
        assert source.calls == ["discovery", "jwks"]
        clock.offset += 2
        await cache.keys_for(("old",), deadline=clock.deadline())
        assert source.calls == ["discovery", "jwks", "discovery", "jwks"]

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["discovery", "jwks"])
def test_cold_outage_cooldown_no_stampede_and_safe_errors(snapshots, failure, monkeypatch):
    async def run():
        clock = Clock(monkeypatch)
        source = Source(snapshots[0])
        source.failure = failure
        cache = OidcKeyCache(source)
        await asyncio.gather(
            *(
                error(503, cache.keys_for((f"unknown-{i}",), deadline=clock.deadline()))
                for i in range(100)
            )
        )
        assert source.calls == (["discovery"] if failure == "discovery" else ["discovery", "jwks"])
        source.failure = None
        await error(503, cache.keys_for(("old",), deadline=clock.deadline()))
        clock.offset += 31
        assert await cache.keys_for(("old",), deadline=clock.deadline()) is snapshots[0]

    asyncio.run(run())


def test_failed_refresh_keeps_known_unexpired_keys_without_extending_ttl(snapshots, monkeypatch):
    async def run():
        clock = Clock(monkeypatch)
        source = Source(snapshots[0])
        cache = OidcKeyCache(source)
        await cache.keys_for(("old",), deadline=clock.deadline())
        clock.offset += 31
        source.failure = "jwks"
        await error(503, cache.keys_for(("new",), deadline=clock.deadline()))
        assert await cache.keys_for(("old",), deadline=clock.deadline()) is snapshots[0]
        await error(503, cache.keys_for(("new",), deadline=clock.deadline()))
        assert source.calls == ["discovery", "jwks", "jwks"]
        clock.offset += 270
        source.failure = "discovery"
        await error(503, cache.keys_for(("old",), deadline=clock.deadline()))
        assert source.calls[-1] == "discovery"

    asyncio.run(run())


def test_concurrent_single_flight_and_waiter_deadline_does_not_cancel_leader(snapshots):
    async def run():
        source = Source(snapshots[0])
        source.release.clear()
        cache = OidcKeyCache(source)
        loop = asyncio.get_running_loop()
        leader = asyncio.create_task(cache.keys_for(("old",), deadline=loop.time() + 15))
        await source.entered.wait()
        await error(503, cache.keys_for(("old",), deadline=loop.time() + 0.02))
        assert not leader.done()
        waiters = [
            asyncio.create_task(cache.keys_for(("old",), deadline=loop.time() + 15))
            for _ in range(20)
        ]
        await asyncio.sleep(0)
        source.release.set()
        assert all(result is snapshots[0] for result in await asyncio.gather(leader, *waiters))
        assert source.calls == ["discovery", "jwks"]

    asyncio.run(run())


def test_cancelled_leader_leaves_cooldown_and_releases_lock(snapshots, monkeypatch):
    async def run():
        clock = Clock(monkeypatch)
        source = Source(snapshots[0])
        source.release.clear()
        cache = OidcKeyCache(source)
        leader = asyncio.create_task(cache.keys_for(("old",), deadline=clock.deadline()))
        await source.entered.wait()
        leader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await leader
        await error(503, cache.keys_for(("old",), deadline=clock.deadline()))
        assert source.calls == ["discovery", "jwks"]
        source.release.set()
        clock.offset += 31
        assert await cache.keys_for(("old",), deadline=clock.deadline()) is snapshots[0]

    asyncio.run(run())


def test_known_key_does_not_wait_for_inflight_unknown_refresh(snapshots, monkeypatch):
    async def run():
        clock = Clock(monkeypatch)
        source = Source(snapshots[0])
        cache = OidcKeyCache(source)
        await cache.keys_for(("old",), deadline=clock.deadline())
        clock.offset += 31
        source.entered.clear()
        source.release.clear()
        leader = asyncio.create_task(cache.keys_for(("new",), deadline=clock.deadline()))
        await source.entered.wait()
        assert await cache.keys_for(("old",), deadline=clock.now() + 0.05) is snapshots[0]
        source.keys = snapshots[1]
        source.release.set()
        assert await leader is snapshots[1]

    asyncio.run(run())


@pytest.mark.parametrize(
    "kids", [(), [], "old", ("",), (None,), ("x" * 129,), ("a", "b", "c"), ("a\n",)]
)
def test_bad_hints_rejected_without_io(snapshots, kids):
    async def run():
        source = Source(snapshots[0])
        await error(
            401,
            OidcKeyCache(source).keys_for(kids, deadline=asyncio.get_running_loop().time() + 15),
        )
        assert source.calls == []

    asyncio.run(run())


@pytest.mark.parametrize(
    "deadline", [0, -1, True, None, "20", float("nan"), float("inf"), 10**400, 2**53]
)
def test_bad_deadline_before_io_and_even_fast_path(snapshots, deadline):
    async def run():
        source = Source(snapshots[0])
        cache = OidcKeyCache(source)
        await error(503, cache.keys_for(("old",), deadline=deadline))
        assert source.calls == []
        await cache.keys_for(("old",), deadline=asyncio.get_running_loop().time() + 15)
        await error(503, cache.keys_for(("old",), deadline=deadline))
        assert source.calls == ["discovery", "jwks"]

    asyncio.run(run())


def test_exact_cooldown_and_ttl_boundaries(snapshots, monkeypatch):
    async def run():
        loop = asyncio.get_running_loop()
        now = [loop.time()]
        monkeypatch.setattr(loop, "time", lambda: now[0])
        started = now[0]
        source = Source(snapshots[0])
        cache = OidcKeyCache(source)
        await cache.keys_for(("old",), deadline=now[0] + 15)
        now[0] = started + 29.999
        await error(401, cache.keys_for(("new",), deadline=now[0] + 15))
        assert source.calls == ["discovery", "jwks"]
        now[0] = started + 30
        source.failure = "jwks"
        await error(503, cache.keys_for(("new",), deadline=now[0] + 15))
        assert source.calls == ["discovery", "jwks", "jwks"]
        now[0] = started + 299.999
        assert await cache.keys_for(("old",), deadline=now[0] + 15) is snapshots[0]
        now[0] = started + 300
        await error(503, cache.keys_for(("old",), deadline=now[0] + 15))
        assert source.calls == ["discovery", "jwks", "jwks", "discovery", "jwks"]

    asyncio.run(run())


def test_cancelled_waiter_never_cancels_leader(snapshots):
    async def run():
        source = Source(snapshots[0])
        source.release.clear()
        cache = OidcKeyCache(source)
        deadline = asyncio.get_running_loop().time() + 15
        leader = asyncio.create_task(cache.keys_for(("old",), deadline=deadline))
        await source.entered.wait()
        waiter = asyncio.create_task(cache.keys_for(("old",), deadline=deadline))
        await asyncio.sleep(0)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert not leader.done()
        source.release.set()
        assert await leader is snapshots[0]
        assert source.calls == ["discovery", "jwks"]

    asyncio.run(run())


def test_deadline_rechecked_after_provider_without_await(snapshots, monkeypatch):
    async def run():
        loop = asyncio.get_running_loop()
        now = [loop.time()]
        monkeypatch.setattr(loop, "time", lambda: now[0])

        class Delayed(Source):
            async def jwks(self, *, deadline):
                self.calls.append("jwks")
                now[0] += 16
                return self.keys

        source = Delayed(snapshots[0])
        cache = OidcKeyCache(source)
        await error(503, cache.keys_for(("old",), deadline=now[0] + 15))
        await error(503, cache.keys_for(("old",), deadline=now[0] + 15))
        assert source.calls == ["discovery", "jwks"]

    asyncio.run(run())


def test_invalid_provider_result_never_replaces_snapshot(snapshots, monkeypatch):
    async def run():
        clock = Clock(monkeypatch)
        source = Source(snapshots[0])
        cache = OidcKeyCache(source)
        await cache.keys_for(("old",), deadline=clock.deadline())
        clock.offset += 31
        source.keys = None
        await error(503, cache.keys_for(("new",), deadline=clock.deadline()))
        assert await cache.keys_for(("old",), deadline=clock.deadline()) is snapshots[0]

    asyncio.run(run())


def test_cache_cannot_be_reused_on_another_event_loop(snapshots):
    source = Source(snapshots[0])
    cache = OidcKeyCache(source)

    async def first():
        await cache.keys_for(("old",), deadline=asyncio.get_running_loop().time() + 15)

    async def second():
        await error(503, cache.keys_for(("old",), deadline=asyncio.get_running_loop().time() + 15))

    asyncio.run(first())
    asyncio.run(second())
    assert source.calls == ["discovery", "jwks"]


def test_two_distinct_keys_and_fresh_keys_with_expired_discovery(snapshots, monkeypatch):
    async def run():
        clock = Clock(monkeypatch)
        source = Source(snapshots[0])
        cache = OidcKeyCache(source)
        await cache.keys_for(("old",), deadline=clock.deadline())
        clock.offset += 31
        source.keys = snapshots[3]
        assert await cache.keys_for(("old", "new"), deadline=clock.deadline()) is snapshots[3]
        clock.offset += 270  # discovery age301, JWKS age270
        source.failure = "discovery"
        assert await cache.keys_for(("new", "old"), deadline=clock.deadline()) is snapshots[3]
        assert source.calls == ["discovery", "jwks", "jwks"]

    asyncio.run(run())


@pytest.mark.parametrize("kids", [("old",), ()])
@pytest.mark.parametrize("ambient", [asyncio.CancelledError, ValueError])
def test_safe_failure_inside_callers_exception_handler(snapshots, kids, ambient):
    async def run():
        source = Source(snapshots[0])
        source.failure = "jwks"
        try:
            raise ambient(MARKER)
        except ambient:
            await error(
                503 if kids else 401,
                OidcKeyCache(source).keys_for(
                    kids, deadline=asyncio.get_running_loop().time() + 15
                ),
            )

    asyncio.run(run())
