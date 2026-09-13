import pytest
from app.identity.application.security import (
    BruteForceGuard,
    BruteForcePolicy,
    InMemoryRateLimitStore,
    RedisRateLimitStore,
)
from app.identity.domain.exceptions import BruteForceProtectionTriggeredError


@pytest.mark.asyncio
async def test_allows_attempts_within_the_limit() -> None:
    guard = BruteForceGuard(store=InMemoryRateLimitStore(), policy=BruteForcePolicy(max_attempts_per_window=3))
    for _ in range(3):
        await guard.check(ip_address="203.0.113.9")


@pytest.mark.asyncio
async def test_blocks_attempts_beyond_the_limit() -> None:
    guard = BruteForceGuard(store=InMemoryRateLimitStore(), policy=BruteForcePolicy(max_attempts_per_window=3))
    for _ in range(3):
        await guard.check(ip_address="203.0.113.9")

    with pytest.raises(BruteForceProtectionTriggeredError):
        await guard.check(ip_address="203.0.113.9")


@pytest.mark.asyncio
async def test_tracks_each_ip_independently() -> None:
    guard = BruteForceGuard(store=InMemoryRateLimitStore(), policy=BruteForcePolicy(max_attempts_per_window=1))
    await guard.check(ip_address="203.0.113.9")
    await guard.check(ip_address="203.0.113.10")  # different IP, own budget


@pytest.mark.asyncio
async def test_login_and_mfa_scopes_have_independent_budgets() -> None:
    guard = BruteForceGuard(
        store=InMemoryRateLimitStore(),
        policy=BruteForcePolicy(max_attempts_per_window=1),
    )
    await guard.check(ip_address="203.0.113.9", scope="login")
    await guard.check(ip_address="203.0.113.9", scope="mfa_challenge:123")


class _FakeRedis:
    def __init__(self) -> None:
        self.args = None

    async def eval(self, *args):
        self.args = args
        return 4


@pytest.mark.asyncio
async def test_redis_rate_limit_store_uses_atomic_script_and_namespaced_key() -> None:
    redis = _FakeRedis()
    store = RedisRateLimitStore(redis)

    count = await store.increment_and_get("login_attempts:203.0.113.9", window_seconds=300)

    assert count == 4
    assert redis.args[1:] == (1, "rate_limit:login_attempts:203.0.113.9", 300)
