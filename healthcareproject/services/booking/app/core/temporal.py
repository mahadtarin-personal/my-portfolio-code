import asyncio
import logging

from temporalio.client import Client
from temporalio.service import RPCError

logger = logging.getLogger("booking.temporal")


async def connect_with_retry(
    address: str, namespace: str, *, attempts: int = 15, delay: float = 2.0
) -> Client:
    """Temporal's own container may still be starting up when a caller
    tries to connect — depends_on only waits for the container process to
    start, not for the gRPC frontend to actually accept connections."""
    for attempt in range(1, attempts + 1):
        try:
            return await Client.connect(address, namespace=namespace)
        except RPCError:
            logger.info("temporal not ready yet (attempt %d/%d), retrying...", attempt, attempts)
            await asyncio.sleep(delay)
    raise RuntimeError(f"could not connect to temporal at {address} after {attempts} attempts")
