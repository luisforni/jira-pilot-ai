"""Background task: subscribe to Redis and broadcast events to WebSocket clients."""
import asyncio
import json

import structlog
import redis.asyncio as aioredis

from api.ws.manager import manager
from core.config import settings
from core.events import PIPELINE_CHANNEL

log = structlog.get_logger()


async def redis_subscriber() -> None:
    while True:
        try:
            r = aioredis.from_url(settings.redis_url, decode_responses=True)
            pubsub = r.pubsub()
            await pubsub.subscribe(PIPELINE_CHANNEL)
            log.info("redis_subscriber_started", channel=PIPELINE_CHANNEL)

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    room = data.get("task_id", "")
                    await manager.broadcast(data, room=room)
                except Exception as exc:
                    log.warning("subscriber_message_error", error=str(exc))

        except asyncio.CancelledError:
            log.info("redis_subscriber_cancelled")
            break
        except Exception as exc:
            log.warning("redis_subscriber_error", error=str(exc))
            await asyncio.sleep(3)
