from __future__ import annotations

import enum
import logging
from typing import Any

import aiohttp
from yarl import URL

from .models import Cluster

logger = logging.getLogger(__name__)


class NotificationType(str, enum.Enum):
    CLUSTER_UPDATING = "cluster_updating"
    CLUSTER_UPDATE_SUCCEEDED = "cluster_update_succeeded"
    CLUSTER_UPDATE_FAILED = "cluster_update_failed"


class ConfigClient:
    def __init__(
        self, url: URL, trace_configs: list[aiohttp.TraceConfig] | None = None
    ) -> None:
        self._base_url = url
        self._trace_configs = trace_configs
        self._session: aiohttp.ClientSession | None = None

    def _create_headers(self, token: str | None = None) -> dict[str, Any]:
        result = {}
        if token:
            result["Authorization"] = f"Bearer {token}"
        return result

    async def __aenter__(self) -> "ConfigClient":
        self._session = aiohttp.ClientSession(trace_configs=self._trace_configs)
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
        await self.close()

    async def close(self) -> None:
        assert self._session
        await self._session.close()

    async def get_cluster(self, cluster_name: str, token: str | None = None) -> Cluster:
        assert self._session
        async with self._session.get(
            (self._base_url / "api/v1/clusters" / cluster_name).with_query(
                include="all"
            ),
            headers=self._create_headers(token=token),
        ) as response:
            response.raise_for_status()
            payload = await response.json()
            return Cluster(payload)

    async def patch_cluster(
        self, cluster_name: str, payload: dict[str, Any], token: str | None = None
    ) -> None:
        assert self._session
        async with self._session.patch(
            self._base_url / "api/v1/clusters" / cluster_name,
            json=payload,
            headers=self._create_headers(token=token),
        ) as response:
            response.raise_for_status()

    async def send_notification(
        self,
        cluster_name: str,
        notification_type: NotificationType,
        token: str | None = None,
    ) -> None:
        assert self._session
        async with self._session.post(
            self._base_url / "api/v1/clusters" / cluster_name / "notifications",
            headers=self._create_headers(token=token),
            json={"notification_type": notification_type.value},
        ) as response:
            response.raise_for_status()
