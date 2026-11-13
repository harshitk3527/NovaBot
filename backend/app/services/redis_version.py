from uuid import UUID

from redis.asyncio import Redis

from app.core.config import get_settings


def version_key(tenant_id: UUID) -> str:
    return f"kb_version:{tenant_id}"


async def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


async def increment_kb_version(tenant_id: UUID) -> int:
    redis = await get_redis()
    try:
        return int(await redis.incr(version_key(tenant_id)))
    finally:
        await redis.aclose()


async def get_kb_version(tenant_id: UUID) -> int:
    redis = await get_redis()
    try:
        value = await redis.get(version_key(tenant_id))
        return int(value or 0)
    finally:
        await redis.aclose()
