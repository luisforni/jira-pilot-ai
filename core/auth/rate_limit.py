from datetime import datetime, timezone

import structlog
import redis.asyncio as aioredis

from core.config import settings
from core.models.auth import PLAN_MONTHLY_LIMITS

log = structlog.get_logger()

_KEY_PREFIX = "jira_pilot:rate:"


def _month_key(org_id: str) -> str:
    now = datetime.now(timezone.utc)
    return f"{_KEY_PREFIX}{org_id}:{now.year}:{now.month:02d}"


async def check_and_increment(org_id: str, plan: str) -> tuple[bool, int, int]:
    """
    Returns (allowed, current_count, limit).
    Increments counter if allowed.
    """
    limit = PLAN_MONTHLY_LIMITS.get(plan, 50)
    key = _month_key(org_id)

    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        count = await r.get(key)
        current = int(count) if count else 0

        if current >= limit:
            await r.aclose()
            return False, current, limit

        pipe = r.pipeline()
        pipe.incr(key)
        # expire at end of month (max 31 days)
        pipe.expire(key, 31 * 24 * 3600)
        await pipe.execute()
        await r.aclose()

        return True, current + 1, limit

    except Exception as exc:
        log.warning("rate_limit_redis_error", error=str(exc))
        # Fail open — don't block on Redis issues
        return True, 0, limit


async def get_usage(org_id: str) -> int:
    key = _month_key(org_id)
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        count = await r.get(key)
        await r.aclose()
        return int(count) if count else 0
    except Exception:
        return 0
