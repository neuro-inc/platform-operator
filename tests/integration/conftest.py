from __future__ import annotations

import pytest

from platform_operator.helm_client import HelmClient


@pytest.fixture
async def helm_client(kube_context: str, kube_namespace: str) -> HelmClient:
    return HelmClient(kube_context=kube_context, namespace=kube_namespace)
