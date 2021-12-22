from __future__ import annotations

import asyncio
import json
import logging
import ssl
from base64 import b64decode
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import aiohttp
from yarl import URL

from .models import KubeClientAuthType, KubeConfig

logger = logging.getLogger(__name__)

PLATFORM_GROUP = "neuromation.io"
PLATFORM_API_VERSION = "v1"
PLATFORM_PLURAL = "platforms"


class PlatformPhase(str, Enum):
    PENDING = "Pending"
    DEPLOYING = "Deploying"
    DELETING = "Deleting"
    DEPLOYED = "Deployed"
    FAILED = "Failed"


class PlatformConditionType(str, Enum):
    OBS_CSI_DRIVER_DEPLOYED = "ObsCsiDriverDeployed"
    PLATFORM_DEPLOYED = "PlatformDeployed"
    CERTIFICATE_CREATED = "CertificateCreated"
    CLUSTER_CONFIGURED = "ClusterConfigured"


class PlatformConditionStatus(str, Enum):
    TRUE = "True"
    FALSE = "False"
    # The state is unknown, platform deployment might have succeeded
    # or failed but we don't know because timeout have occurred
    UNKNOWN = "Unknown"


class Endpoints:
    def __init__(self, url: URL) -> None:
        self._url = url

    @property
    def nodes(self) -> URL:
        return self._url / "api/v1/nodes"

    def node(self, name: str) -> URL:
        return self.nodes / name

    @property
    def namespaces(self) -> URL:
        return self._url / "api/v1/namespaces"

    def namespace(self, name: str) -> URL:
        return self.namespaces / name

    def services(self, namespace: str) -> URL:
        return self.namespace(namespace) / "services"

    def service(self, namespace: str, name: str) -> URL:
        return self.services(namespace) / name

    def service_accounts(self, namespace: str) -> URL:
        return self.namespace(namespace) / "serviceaccounts"

    def service_account(self, namespace: str, name: str) -> URL:
        return self.service_accounts(namespace) / name

    def secrets(self, namespace: str) -> URL:
        return self.namespace(namespace) / "secrets"

    def secret(self, namespace: str, name: str) -> URL:
        return self.secrets(namespace) / name

    def pods(self, namespace: str) -> URL:
        return self.namespace(namespace) / "pods"

    def platforms(self, namespace: str) -> URL:
        return (
            self._url
            / f"apis/{PLATFORM_GROUP}/{PLATFORM_API_VERSION}/namespaces"
            / f"{namespace}/{PLATFORM_PLURAL}"
        )

    def platform(self, namespace: str, name: str) -> URL:
        return self.platforms(namespace) / name


class Node:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    @property
    def container_runtime(self) -> str:
        version = self._payload["status"]["nodeInfo"]["containerRuntimeVersion"]
        end = version.find("://")
        return version[0:end]


class Service(dict[str, Any]):
    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__(payload)

    @property
    def cluster_ip(self) -> str:
        return self["spec"]["clusterIP"]

    @property
    def load_balancer_host(self) -> str:
        return self["status"]["loadBalancer"]["ingress"][0]["hostname"]


class KubeClient:
    def __init__(
        self,
        config: KubeConfig,
        trace_configs: list[aiohttp.TraceConfig] | None = None,
    ) -> None:
        self._config = config
        self._trace_configs = trace_configs
        self._session: aiohttp.ClientSession | None = None
        self._endpoints = Endpoints(config.url)

    @property
    def _is_ssl(self) -> bool:
        return self._config.url.scheme == "https"

    def _create_ssl_context(self) -> ssl.SSLContext | None:
        if not self._is_ssl:
            return None
        cert_authority_data_pem = ""
        if self._config.cert_authority_data_pem:
            cert_authority_data_pem = self._config.cert_authority_data_pem
        if self._config.cert_authority_path:
            cert_authority_data_pem = self._config.cert_authority_path.read_text()
        assert cert_authority_data_pem
        ssl_context = ssl.create_default_context(cadata=cert_authority_data_pem)
        if self._config.auth_type == KubeClientAuthType.CERTIFICATE:
            assert self._config.auth_cert_path
            assert self._config.auth_cert_key_path
            ssl_context.load_cert_chain(
                str(self._config.auth_cert_path), str(self._config.auth_cert_key_path)
            )
        return ssl_context

    async def __aenter__(self) -> "KubeClient":
        headers = {}
        if self._config.auth_type == KubeClientAuthType.TOKEN:
            assert self._config.auth_token or self._config.auth_token_path
            if self._config.auth_token:
                headers = {"Authorization": "Bearer " + self._config.auth_token}
            if self._config.auth_token_path:
                headers = {
                    "Authorization": "Bearer "
                    + self._config.auth_token_path.read_text()
                }
        connector = aiohttp.TCPConnector(
            limit=self._config.conn_pool_size, ssl=self._create_ssl_context()
        )
        timeout = aiohttp.ClientTimeout(
            connect=self._config.conn_timeout_s, total=self._config.read_timeout_s
        )
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            trace_configs=self._trace_configs,
            headers=headers,
        )
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
        assert self._session
        await self._session.close()
        self._session = None

    async def get_node(self, name: str) -> Node:
        assert self._session
        async with self._session.get(self._endpoints.node(name)) as response:
            response.raise_for_status()
            payload = await response.json()
            return Node(payload)

    async def create_namespace(self, name: str) -> None:
        assert self._session
        async with self._session.post(
            self._endpoints.namespaces, json={"metadata": {"name": name}}
        ) as response:
            response.raise_for_status()

    async def delete_namespace(self, name: str) -> None:
        assert self._session
        async with self._session.delete(
            self._endpoints.namespace(name), json={"propagationPolicy": "Background"}
        ) as response:
            response.raise_for_status()

    async def get_service(self, namespace: str, name: str) -> Service:
        assert self._session
        async with self._session.get(
            self._endpoints.service(namespace, name)
        ) as response:
            response.raise_for_status()
            payload = await response.json()
            return Service(payload)

    async def get_service_account(self, namespace: str, name: str) -> dict[str, Any]:
        assert self._session
        async with self._session.get(
            self._endpoints.service_account(namespace, name)
        ) as response:
            response.raise_for_status()
            payload = await response.json()
            return payload

    async def update_service_account_image_pull_secrets(
        self, namespace: str, name: str, image_pull_secrets: Sequence[str]
    ) -> None:
        assert self._session
        async with self._session.patch(
            self._endpoints.service_account(namespace, name),
            headers={"Content-Type": "application/merge-patch+json"},
            data=json.dumps(
                {"imagePullSecrets": [{"name": name} for name in image_pull_secrets]}
            ),
        ) as response:
            response.raise_for_status()

    async def get_secret(self, namespace: str, name: str) -> dict[str, Any]:
        assert self._session
        async with self._session.get(
            self._endpoints.secret(namespace, name)
        ) as response:
            response.raise_for_status()
            payload = await response.json()
            return self._decode_secret_data(payload)

    def _decode_secret_data(self, secret: dict[str, Any]) -> dict[str, Any]:
        secret = dict(**secret)
        decoded_data: dict[str, str] = {}
        for key, value in secret["data"].items():
            decoded_data[key] = b64decode(value.encode("utf-8")).decode("utf-8")
        secret["data"] = decoded_data
        return secret

    async def get_pods(
        self,
        namespace: str,
        label_selector: dict[str, str] | None = None,
        limit: int = 100,
    ) -> Sequence[dict[str, Any]]:
        assert limit
        query = {"limit": str(limit)}
        if label_selector:
            query["labelSelector"] = ",".join(
                f"{key}={value}" for key, value in label_selector.items()
            )
        assert self._session
        async with self._session.get(
            self._endpoints.pods(namespace).with_query(**query)
        ) as response:
            response.raise_for_status()
            payload = await response.json()
            return payload["items"]

    async def wait_till_pods_deleted(
        self,
        namespace: str,
        label_selector: dict[str, str] | None = None,
        interval_secs: int = 5,
    ) -> None:
        while True:
            payload = await self.get_pods(namespace, label_selector, 1)
            if not payload:
                break
            await asyncio.sleep(interval_secs)

    async def create_platform(self, namespace: str, payload: dict[str, Any]) -> None:
        assert self._session
        async with self._session.post(
            self._endpoints.platforms(namespace=namespace), json=payload
        ) as response:
            response.raise_for_status()

    async def delete_platform(self, namespace: str, name: str) -> None:
        assert self._session
        async with self._session.delete(
            self._endpoints.platform(namespace, name)
        ) as response:
            response.raise_for_status()

    async def get_platform_status(
        self, namespace: str, name: str
    ) -> dict[str, Any] | None:
        assert self._session
        async with self._session.get(
            self._endpoints.platform(namespace, name) / "status"
        ) as response:
            response.raise_for_status()
            payload = await response.json()
            if "status" not in payload:
                return None
            status_payload = payload["status"]
            return status_payload

    async def update_platform_status(
        self, namespace: str, name: str, payload: dict[str, Any]
    ) -> None:
        assert self._session
        async with self._session.patch(
            self._endpoints.platform(namespace, name) / "status",
            headers={"Content-Type": "application/merge-patch+json"},
            data=json.dumps({"status": payload}),
        ) as response:
            response.raise_for_status()


class PlatformCondition(dict[str, Any]):
    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__(payload)

    @property
    def type(self) -> str:
        return self["type"]

    @type.setter
    def type(self, value: str) -> None:
        self["type"] = value

    @property
    def status(self) -> str:
        return self["status"]

    @status.setter
    def status(self, value: str) -> None:
        self["status"] = value

    @property
    def last_transition_time(self) -> str:
        return self["lastTransitionTime"]

    @last_transition_time.setter
    def last_transition_time(self, value: str) -> None:
        self["lastTransitionTime"] = value


class PlatformStatus(dict[str, Any]):
    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__(payload)

    @property
    def phase(self) -> str:
        return self["phase"]

    @phase.setter
    def phase(self, value: str) -> None:
        self["phase"] = value

    @property
    def retries(self) -> int:
        return self["retries"]

    @retries.setter
    def retries(self, value: int) -> None:
        self["retries"] = value

    @property
    def conditions(self) -> dict[str, PlatformCondition]:
        return self["conditions"]


class PlatformStatusManager:
    def __init__(self, kube_client: KubeClient, namespace: str) -> None:
        self._kube_client = kube_client
        self._namespace = namespace
        self._status: dict[str, PlatformStatus] = {}

    async def _load(self, name: str) -> None:
        if self._status.get(name):
            return
        payload = await self._kube_client.get_platform_status(
            namespace=self._namespace, name=name
        )
        if payload:
            self._status[name] = PlatformStatus(self._deserialize(payload))
        else:
            self._status[name] = PlatformStatus(
                {
                    "phase": PlatformPhase.PENDING.value,
                    "retries": 0,
                    "conditions": {},
                }
            )

    def _deserialize(cls, payload: dict[str, Any]) -> PlatformStatus:
        status = {
            "phase": payload["phase"],
            "retries": payload["retries"],
            "conditions": cls._deserialize_conditions(payload["conditions"]),
        }
        return PlatformStatus(status)

    def _deserialize_conditions(
        self, payload: Sequence[dict[str, Any]]
    ) -> dict[str, PlatformCondition]:
        result: dict[str, PlatformCondition] = {}

        for p in payload:
            result[p["type"]] = PlatformCondition(p)

        return result

    async def _save(self, name: str) -> None:
        await self._kube_client.update_platform_status(
            namespace=self._namespace,
            name=name,
            payload=self._serialize(self._status[name]),
        )

    def _serialize(self, status: PlatformStatus) -> dict[str, Any]:
        return {
            "phase": status.phase,
            "retries": status.retries,
            "conditions": self._serialize_conditions(status.conditions),
        }

    def _serialize_conditions(
        self, conditions: dict[str, PlatformCondition]
    ) -> list[PlatformCondition]:
        result: list[PlatformCondition] = []

        for type in PlatformConditionType:
            if type in conditions:
                result.append(conditions[type])

        return result

    def _now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    async def start_deployment(self, name: str, retry: int | None = None) -> None:
        await self._load(name)
        self._status[name].phase = PlatformPhase.DEPLOYING.value
        self._status[name].retries = retry or 0
        await self._save(name)

    async def complete_deployment(self, name: str) -> None:
        await self._load(name)
        self._status[name].phase = PlatformPhase.DEPLOYED.value
        await self._save(name)

    async def fail_deployment(self, name: str) -> None:
        await self._load(name)
        self._status[name].phase = PlatformPhase.FAILED.value
        await self._save(name)

    async def start_deletion(self, name: str) -> None:
        await self._load(name)
        self._status[name].phase = PlatformPhase.DELETING.value
        await self._save(name)

    @asynccontextmanager
    async def transition(
        self, name: str, type: PlatformConditionType
    ) -> AsyncIterator[None]:
        try:
            logger.info("Started transition to %s condition", type.value)
            condition = PlatformCondition({})
            condition.type = type
            condition.status = PlatformConditionStatus.FALSE
            condition.last_transition_time = self._now()
            self._status[name].conditions[type] = condition
            await self._save(name)
            yield
            condition.status = PlatformConditionStatus.TRUE
            logger.info("Transition to %s succeeded", type.value)
        except asyncio.CancelledError:
            condition.status = PlatformConditionStatus.UNKNOWN
            logger.info("Transition to %s was cancelled", type.value)
            raise
        except Exception:
            condition.status = PlatformConditionStatus.FALSE
            logger.exception("Transition to %s failed", type.value)
            raise
        finally:
            condition.last_transition_time = self._now()
            await self._save(name)

    async def get_phase(self, name: str) -> PlatformPhase:
        await self._load(name)
        return PlatformPhase(self._status[name].phase)
