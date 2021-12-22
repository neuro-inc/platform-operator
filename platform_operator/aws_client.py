from __future__ import annotations

from typing import Any

import aiobotocore.session
from yarl import URL


class AwsElbClient:
    _session = aiobotocore.session.get_session()

    def __init__(
        self,
        region: str,
        access_key_id: str = "",
        secret_access_key: str = "",
        endpoint_url: URL | None = None,
    ) -> None:
        self._region = region
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._endpoint_url = endpoint_url

    async def __aenter__(self, *args: Any, **kwargs: Any) -> "AwsElbClient":
        # On AWS the nodes will be configured to assume the correct role and no
        # credentials need to be passed.
        kwargs = {}
        if self._access_key_id:
            kwargs["aws_access_key_id"] = self._access_key_id
        if self._secret_access_key:
            kwargs["aws_secret_access_key"] = self._secret_access_key
        if self._endpoint_url:
            kwargs["endpoint_url"] = str(self._endpoint_url)
        context = self._session.create_client("elb", region_name=self._region, **kwargs)
        self._client = await context.__aenter__()
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
        await self._client.__aexit__(*args, **kwargs)

    async def create_load_balancer(self, **kwargs: Any) -> dict[str, str]:
        return await self._client.create_load_balancer(**kwargs)

    async def delete_load_balancer(self, **kwargs: Any) -> None:
        await self._client.delete_load_balancer(**kwargs)

    async def get_load_balancer_by_dns_name(
        self, dns_name: str
    ) -> dict[str, Any] | None:
        paginator = self._client.get_paginator("describe_load_balancers")
        async for page in paginator.paginate():
            for lb in page.get("LoadBalancerDescriptions", []):
                if lb["DNSName"] == dns_name:
                    return lb
        return None
