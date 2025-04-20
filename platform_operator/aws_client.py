from __future__ import annotations

import logging
from typing import Any

import aiobotocore.session
from aiobotocore.config import AioConfig
from aiobotocore.session import ClientCreatorContext
from yarl import URL

logger = logging.getLogger(__name__)


class BaseAwsClient:
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

    def _create_client(self, service_name: str, **kwargs: Any) -> ClientCreatorContext:
        kwargs = {"region_name": self._region}
        if self._access_key_id:
            kwargs["aws_access_key_id"] = self._access_key_id
        if self._secret_access_key:
            kwargs["aws_secret_access_key"] = self._secret_access_key
        if self._endpoint_url:
            kwargs["endpoint_url"] = str(self._endpoint_url)
        return self._session.create_client(service_name, **kwargs)


class AwsElbClient(BaseAwsClient):
    async def __aenter__(self, *args: Any, **kwargs: Any) -> AwsElbClient:
        # On AWS the nodes will be configured to assume the correct role and no
        # credentials need to be passed.
        context = self._create_client("elbv2", **kwargs)
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
            for lb in page.get("LoadBalancers", []):
                if lb["DNSName"] == dns_name:
                    return lb
        return None


class S3Client(BaseAwsClient):
    async def __aenter__(self, *args: Any, **kwargs: Any) -> S3Client:
        context = self._session.create_client(
            "s3",
            config=AioConfig(retries={"mode": "standard"}),
        )
        self._client = await context.__aenter__()
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
        await self._client.__aexit__(*args, **kwargs)

    async def is_bucket_exists(self, bucket_name: str) -> bool:
        try:
            await self._client.head_bucket(Bucket=bucket_name)
        except self._client.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise Exception(f"Error checking bucket existence: {e}")
        return True

    async def create_bucket(self, bucket_name: str) -> None:
        try:
            if await self.is_bucket_exists(bucket_name):
                return
            await self._client.create_bucket(Bucket=bucket_name)
            logger.info("Bucket %r created", bucket_name)
        except self._client.exceptions.ClientError as e:
            logger.error("Error creating bucket %r: %s", bucket_name, e)
