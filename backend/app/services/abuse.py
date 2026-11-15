from uuid import UUID

from redis.asyncio import Redis

from app.core.config import get_settings


def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


async def allow_request(scope: str, identifier: str, limit: int) -> bool:
    redis = _redis()
    key = f"novabot:rate:{scope}:{identifier}"
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, get_settings().rate_limit_window_seconds)
        return count <= limit
    except Exception:
        return True
    finally:
        await redis.aclose()


async def reserve_token_budget(user_id: UUID, estimated_tokens: int) -> bool:
    redis = _redis()
    settings = get_settings()
    key = f"novabot:budget:{user_id}"
    try:
        total = await redis.incrby(key, max(1, estimated_tokens))
        if total == estimated_tokens:
            await redis.expire(key, 86400)
        return total <= settings.daily_token_budget
    except Exception:
        return True
    finally:
        await redis.aclose()


async def login_locked(email: str) -> bool:
    redis = _redis()
    try:
        return bool(await redis.exists(f"novabot:login-lock:{email.lower()}"))
    except Exception:
        return False
    finally:
        await redis.aclose()


async def record_login_failure(email: str) -> None:
    redis = _redis()
    settings = get_settings()
    key = f"novabot:login-fail:{email.lower()}"
    try:
        failures = await redis.incr(key)
        await redis.expire(key, settings.login_lockout_seconds)
        if failures >= settings.login_failure_limit:
            await redis.setex(
                f"novabot:login-lock:{email.lower()}",
                settings.login_lockout_seconds,
                "1",
            )
    except Exception:
        return
    finally:
        await redis.aclose()


async def clear_login_failures(email: str) -> None:
    redis = _redis()
    try:
        await redis.delete(f"novabot:login-fail:{email.lower()}", f"novabot:login-lock:{email.lower()}")
    except Exception:
        return
    finally:
        await redis.aclose()
