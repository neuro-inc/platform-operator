import enum
import logging
from types import SimpleNamespace
from typing import Any, Dict, Optional

import aiohttp
from yarl import URL

from .models import Cluster


logger = logging.getLogger(__name__)


class NotificationType(str, enum.Enum):
    CLUSTER_UPDATING = "cluster_updating"
    CLUSTER_UPDATE_SUCCEEDED = "cluster_update_succeeded"
    CLUSTER_UPDATE_FAILED = "cluster_update_failed"


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

    async def patch_cluster(
        self, cluster_name: str, token: str, payload: Dict[str, Any]
    ) -> None:
        assert self._session
        async with self._session.patch(
            self._base_url / "api/v1/clusters" / cluster_name,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        ) as response:
            response.raise_for_status()

    async def send_notification(
        self, cluster_name: str, token: str, notification_type: NotificationType
    ) -> None:
        assert self._session
        async with self._session.post(
            self._base_url / "api/v1/clusters" / cluster_name / "notifications",
            headers={"Authorization": f"Bearer {token}"},
            json={"notification_type": notification_type.value},
        ) as response:
            response.raise_for_status()
