import json

import structlog
import redis.asyncio as aioredis

from core.config import settings

log = structlog.get_logger()

PIPELINE_CHANNEL = "jira_pilot:pipeline_events"


async def publish(event_type: str, **data) -> None:
    """Publish a pipeline event to Redis. Fire-and-forget."""
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        payload = json.dumps({"type": event_type, **data})
        await r.publish(PIPELINE_CHANNEL, payload)
        await r.aclose()
    except Exception as exc:
        log.warning("event_publish_failed", event_type=event_type, error=str(exc))
