import asyncio
from base64 import b64decode

from .consul_client import ConsulClient


LOCK_KEY = "platform"
RELEASE_NAME = "platform-operator"


async def start_operator_deployment(
    consul_client: ConsulClient, release_revision: int
) -> None:
    if release_revision == 1:
        # `helm install` was run, consul has not been deployed yet.
        return

    try:
        await asyncio.wait_for(consul_client.wait_healthy(sleep_s=0.5), 10)
    except asyncio.TimeoutError:
        # Consul has not been deployed yet.
        # Either operator has not been deployed yet or previous deployment has failed.
        # It is safe to proceed, helm won't allow upgrade same chart in parallel.
        return

    session_id = await consul_client.create_session(ttl_s=10 * 60)
    lock_value = _get_lock_value(release_revision)
    acquire_lock_future = consul_client.acquire_lock(
        LOCK_KEY, lock_value, session_id=session_id, sleep_s=5
    )
    await asyncio.wait_for(acquire_lock_future, 30 * 60)


async def end_operator_deployment(
    consul_client: ConsulClient, release_revision: int
) -> None:
    if release_revision == 1:
        # `helm install` was run, there is no lock in consul.
        return

    try:
        await asyncio.wait_for(consul_client.wait_healthy(sleep_s=0.5), 10)
    except asyncio.TimeoutError:
        # Consul has not been deployed yet.
        return

    lock_value_metadata = await consul_client.get_key(LOCK_KEY)
    assert isinstance(lock_value_metadata[0], dict)
    lock_value = b64decode(lock_value_metadata[0]["Value"].encode())

    if _get_lock_value(release_revision) != lock_value:
        # In case lock is expired do nothing.
        # Otherwise can delete lock acquired by other deployment process.
        return

    session_id = lock_value_metadata[0].get("Session")
    if session_id:
        await consul_client.release_lock(LOCK_KEY, lock_value, session_id=session_id)


def _get_lock_value(release_revision: int) -> bytes:
    return f"{RELEASE_NAME}-{release_revision}".encode()
