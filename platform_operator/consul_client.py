import asyncio
import logging
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, AsyncIterator, Dict, Optional, Sequence, Union

import aiohttp
from yarl import URL


logger = logging.getLogger(__name__)


class SessionExpiredError(Exception):
    pass


class LockAcquisitionError(Exception):
    pass


class LockReleaseError(Exception):
    pass


class ConsulClient:
    def __init__(self, url: URL) -> None:
        self._url = url
        self._client: Optional[aiohttp.ClientSession] = None

    async def _on_request_start(
        self,
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceRequestStartParams,
    ) -> None:
        logger.info("Sending %s %s", params.method, params.url)

    async def _on_request_end(
        self,
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceRequestEndParams,
    ) -> None:
        if 400 <= params.response.status:
            logger.warning(
                "Received %s %s %s\n%s",
                params.method,
                params.response.status,
                params.url,
                await params.response.text(),
            )
        else:
            logger.info(
                "Received %s %s %s",
                params.method,
                params.response.status,
                params.url,
            )

    async def __aenter__(self) -> "ConsulClient":
        trace_config = aiohttp.TraceConfig()
        trace_config.on_request_start.append(self._on_request_start)
        trace_config.on_request_end.append(self._on_request_end)
        self._client = aiohttp.ClientSession(trace_configs=[trace_config])
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
        await self.close()

    async def close(self) -> None:
        assert self._client
        await self._client.close()

    async def get_key(
        self, key: str, *, recurse: bool = False, raw: bool = False
    ) -> Union[Sequence[Dict[str, Any]], bytes]:
        assert self._client
        query = {}
        if recurse:
            query["recurse"] = "true"
        if raw:
            query["raw"] = "true"
        async with self._client.get(
            (self._url / "v1/kv" / key).with_query(query or None)
        ) as response:
            response.raise_for_status()
            if raw:
                return await response.read()
            payload = await response.json()
            return payload

    async def put_key(
        self, key: str, value: bytes, *, acquire: str = "", release: str = ""
    ) -> bool:
        assert self._client
        query = {}
        if acquire:
            query["acquire"] = acquire
        if release:
            query["release"] = release
        async with self._client.put(
            (self._url / "v1/kv" / key).with_query(query or None), data=value
        ) as response:
            response.raise_for_status()
            text = await response.text()
            return text.strip() == "true"

    async def delete_key(self, key: str) -> bool:
        assert self._client
        async with self._client.delete(self._url / "v1/kv" / key) as response:
            response.raise_for_status()
            text = await response.text()
            return text.strip() == "true"

    async def get_sessions(self) -> Sequence[Dict[str, Any]]:
        assert self._client
        async with self._client.get(self._url / "v1/session/list") as response:
            response.raise_for_status()
            payload = await response.json()
            return payload

    async def create_session(
        self,
        *,
        ttl_s: int,
        lock_delay_s: Optional[int] = None,
        name: str = "",
        behavior: str = "",
    ) -> str:
        assert self._client
        assert ttl_s >= 10
        assert not lock_delay_s or lock_delay_s > 0
        payload = {"TTL": f"{ttl_s}s"}
        if name:
            payload["Name"] = name
        if behavior:
            payload["Behavior"] = behavior
        if lock_delay_s:
            payload["LockDelay"] = f"{lock_delay_s}s"
        async with self._client.put(
            self._url / "v1/session/create", json=payload
        ) as response:
            response.raise_for_status()
            payload = await response.json()
            return payload["ID"]

    async def delete_session(self, session_id: str) -> bool:
        assert self._client
        async with self._client.put(
            self._url / "v1/session/destroy" / session_id
        ) as response:
            response.raise_for_status()
            text = await response.text()
            return text.strip() == "true"

    @asynccontextmanager
    async def lock_key(
        self,
        key: str,
        value: bytes,
        *,
        ttl_s: int,
        lock_delay_s: Optional[int] = None,
        sleep_s: float = 0.1,
        timeout_s: Optional[float] = None,
    ) -> AsyncIterator[None]:
        session_id = await self.create_session(ttl_s=ttl_s, lock_delay_s=lock_delay_s)
        logger.info("Session %r created", session_id)

        try:
            start_time = time.monotonic()
            while True:
                acquired = await self.put_key(key, value, acquire=session_id)
                if acquired:
                    break
                elapsed_s = time.monotonic() - start_time
                if timeout_s and elapsed_s + sleep_s >= timeout_s:
                    logger.warning(
                        "Failed to acquire lock (%r, %r) before timeout",
                        session_id,
                        key,
                    )
                    raise LockAcquisitionError("Failed to acquire lock before timeout")
                await asyncio.sleep(sleep_s)
            logger.info("Lock (%r, %r) acquired", session_id, key)
            start_time = time.monotonic()  # lock start time
            yield
            elapsed_s = time.monotonic() - start_time
            if elapsed_s >= ttl_s:
                logger.warning("Lock (%r, %r) expired", session_id, key)
                raise SessionExpiredError(f"Session {session_id!r} expired")
            logger.info("Lock (%r, %r) released", session_id, key)
        finally:
            released = await self.delete_session(session_id)
            if not released:
                logger.warning("Failed to destroy session %r", session_id)
                raise LockReleaseError(f"Failed to destroy session {session_id!r}")
            logger.info("Session %r destroyed", session_id)