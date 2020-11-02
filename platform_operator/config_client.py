import logging
from types import SimpleNamespace
from typing import Any, Dict, Optional

import aiohttp
from yarl import URL

from .models import Cluster


logger = logging.getLogger(__name__)


class ConfigClient:
    def __init__(self, url: URL) -> None:
        self._base_url = url
        self._session: Optional[aiohttp.ClientSession] = None

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

    async def __aenter__(self) -> "ConfigClient":
        trace_config = aiohttp.TraceConfig()
        trace_config.on_request_start.append(self._on_request_start)
        trace_config.on_request_end.append(self._on_request_end)
        self._session = aiohttp.ClientSession(trace_configs=[trace_config])
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
        await self.close()

    async def close(self) -> None:
        assert self._session
        await self._session.close()

    async def get_cluster(self, cluster_name: str, token: str) -> Cluster:
        assert self._session
        async with self._session.get(
            (self._base_url / "api/v1/clusters" / cluster_name).with_query(
                include="all"
            ),
            headers={"Authorization": f"Bearer {token}"},
        ) as response:
            response.raise_for_status()
            payload = await response.json()
            return Cluster(payload)

    async def configure_dns(
        self, cluster_name: str, token: str, payload: Dict[str, Any]
    ) -> None:
        assert self._session
        logger.info("cluster '%s' dns configuration: %s", cluster_name, str(payload))
        async with self._session.put(
            self._base_url / "api/v1/clusters" / cluster_name / "dns",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        ) as response:
            response.raise_for_status()

    async def configure_cluster(
        self, cluster_name: str, token: str, payload: Dict[str, Any]
    ) -> None:
        assert self._session
        async with self._session.put(
            self._base_url / "api/v1/clusters" / cluster_name,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        ) as response:
            response.raise_for_status()
