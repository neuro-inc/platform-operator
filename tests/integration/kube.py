import os
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional
from uuid import uuid4

import pytest
import yaml
from yarl import URL

from platform_operator.kube_client import KubeClient
from platform_operator.models import KubeClientAuthType, KubeConfig


@pytest.fixture(scope="session")
def _kube_config_payload() -> Dict[str, Any]:
    kube_config_path = os.path.expanduser("~/.kube/config")
    with open(kube_config_path, "r") as kube_config:
        return yaml.safe_load(kube_config)


@pytest.fixture(scope="session")
def _kube_config_cluster_payload(
    _kube_config_payload: Dict[str, Any]
) -> Dict[str, Any]:
    cluster_name = "minikube"
    clusters = {
        cluster["name"]: cluster["cluster"]
        for cluster in _kube_config_payload["clusters"]
    }
    return clusters[cluster_name]


@pytest.fixture(scope="session")
def _kube_config_user_payload(_kube_config_payload: Dict[str, Any]) -> Dict[str, Any]:
    user_name = "minikube"
    users = {user["name"]: user["user"] for user in _kube_config_payload["users"]}
    return users[user_name]


@pytest.fixture(scope="session")
def _cert_authority_data_pem(_kube_config_cluster_payload: Dict[str, Any]) -> str:
    if "certificate-authority" in _kube_config_cluster_payload:
        return Path(_kube_config_cluster_payload["certificate-authority"]).read_text()
    return _kube_config_cluster_payload["certificate-authority-data"]


@pytest.fixture(scope="session")
def kube_config(
    _kube_config_cluster_payload: Dict[str, Any],
    _kube_config_user_payload: Dict[str, Any],
    _cert_authority_data_pem: Optional[str],
) -> KubeConfig:
    return KubeConfig(
        url=URL(_kube_config_cluster_payload["server"]),
        cert_authority_data_pem=_cert_authority_data_pem,
        auth_type=KubeClientAuthType.CERTIFICATE,
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
