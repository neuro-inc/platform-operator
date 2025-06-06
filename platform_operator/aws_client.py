from __future__ import annotations

import logging
import sys
from typing import Any, Self

import aiobotocore.session
from aiobotocore.config import AioConfig
from aiobotocore.session import ClientCreatorContext
from botocore.exceptions import ClientError as S3ClientError
from yarl import URL


logger = logging.getLogger(__name__)


class UnknownS3Error(Exception):
    pass


def s3_client_error(code: str | int) -> type[Exception]:
    e = sys.exc_info()[1]
    if isinstance(e, S3ClientError) and (
        e.response["Error"]["Code"] == code
        or e.response["ResponseMetadata"]["HTTPStatusCode"] == code
    ):
        return S3ClientError
    return UnknownS3Error


class BaseAwsClient:
    _session = aiobotocore.session.get_session()

    def __init__(
        self,
        region: str,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        endpoint_url: URL | str | None = None,
    ) -> None:
        self._region = region
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._endpoint_url = endpoint_url

    def _create_client(self, service_name: str, **kwargs: Any) -> ClientCreatorContext:
        kwargs.update({"region_name": self._region})
        if self._access_key_id:
            kwargs["aws_access_key_id"] = self._access_key_id
        if self._secret_access_key:
            kwargs["aws_secret_access_key"] = self._secret_access_key
        if self._endpoint_url:
            kwargs["endpoint_url"] = str(self._endpoint_url)
        return self._session.create_client(service_name, **kwargs)


class AwsElbClient(BaseAwsClient):
    async def __aenter__(self, *args: Any, **kwargs: Any) -> Self:
        # On AWS the nodes will be configured to assume the correct role and no
        # credentials need to be passed.
        context = self._create_client("elbv2", **kwargs)
        self._client = await context.__aenter__()
        return self

    async def __aexit__(self, *args: object, **kwargs: Any) -> None:
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
    async def __aenter__(self, *args: Any, **kwargs: Any) -> Self:
        context = self._create_client(
            "s3",
            config=AioConfig(retries={"mode": "standard"}),
        )
        self._client = await context.__aenter__()
        return self

    async def __aexit__(self, *args: object, **kwargs: Any) -> None:
        await self._client.__aexit__(*args, **kwargs)

    async def create_bucket(self, bucket_name: str) -> None:
        try:
            await self._client.create_bucket(Bucket=bucket_name)
            logger.info("Bucket %r created", bucket_name)
        except s3_client_error(409):
            logger.info("Bucket %r already exists", bucket_name)
