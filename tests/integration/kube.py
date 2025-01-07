from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import yaml
from yarl import URL

from platform_operator.kube_client import KubeClient
from platform_operator.models import KubeClientAuthType, KubeConfig


@pytest.fixture(scope="session")
def kube_context() -> str:
    return "minikube"


@pytest.fixture(scope="session")
def _kube_config_payload() -> dict[str, Any]:
    kube_config_path = os.path.expanduser("~/.kube/config")
    with open(kube_config_path) as kube_config:
        return yaml.safe_load(kube_config)


@pytest.fixture(scope="session")
def _kube_config_cluster_payload(
    _kube_config_payload: dict[str, Any]
) -> dict[str, Any]:
    cluster_name = "minikube"
    clusters = {
        cluster["name"]: cluster["cluster"]
        for cluster in _kube_config_payload["clusters"]
    }
    return clusters[cluster_name]


@pytest.fixture(scope="session")
def _kube_config_user_payload(_kube_config_payload: dict[str, Any]) -> dict[str, Any]:
    user_name = "minikube"
    users = {user["name"]: user["user"] for user in _kube_config_payload["users"]}
    return users[user_name]


@pytest.fixture(scope="session")
def _cert_authority_path(
    _kube_config_cluster_payload: dict[str, Any]
) -> Iterator[Path]:
    if "certificate-authority" in _kube_config_cluster_payload:
        yield Path(_kube_config_cluster_payload["certificate-authority"])
        return
    _, path = tempfile.mkstemp()
    Path(path).write_text(_kube_config_cluster_payload["certificate-authority-data"])
    yield Path(path)
    os.remove(path)


@pytest.fixture(scope="session")
def kube_config(
    _kube_config_cluster_payload: dict[str, Any],
    _kube_config_user_payload: dict[str, Any],
    _cert_authority_path: Path | None,
) -> KubeConfig:
    return KubeConfig(
        version="1.14.10",
        url=URL(_kube_config_cluster_payload["server"]),
        auth_type=KubeClientAuthType.CERTIFICATE,
        cert_authority_path=_cert_authority_path,
        auth_cert_path=Path(_kube_config_user_payload["client-certificate"]),
        auth_cert_key_path=Path(_kube_config_user_payload["client-key"]),
    )


@pytest.fixture
async def kube_client(kube_config: KubeConfig) -> AsyncIterator[KubeClient]:
    async with KubeClient(kube_config) as client:
        yield client


@pytest.fixture
async def kube_namespace(kube_client: KubeClient) -> AsyncIterator[str]:
    namespace = f"ns-{str(uuid4())}"
    try:
        await kube_client.create_namespace(namespace)
        yield namespace
    finally:
        await kube_client.delete_namespace(namespace)
