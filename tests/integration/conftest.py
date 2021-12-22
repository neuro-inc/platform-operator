from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from yarl import URL

from platform_operator.consul_client import ConsulClient
from platform_operator.helm_client import HelmClient


@pytest.fixture
async def helm_client(kube_context: str, kube_namespace: str) -> HelmClient:
    return HelmClient(kube_context=kube_context, namespace=kube_namespace)


@pytest.fixture
async def consul_client() -> AsyncIterator[ConsulClient]:
    async with ConsulClient(URL("http://localhost:8500")) as client:
        yield client
