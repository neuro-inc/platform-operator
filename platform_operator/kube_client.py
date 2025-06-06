from __future__ import annotations

import asyncio
import json
import logging
import ssl
from base64 import b64decode, b64encode
from collections.abc import AsyncIterator, Iterable, Sequence
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from enum import Enum
from time import time
from typing import Any, Self

import aiohttp
from yarl import URL

from .models import KubeClientAuthType, KubeConfig


logger = logging.getLogger(__name__)

PLATFORM_GROUP = "neuromation.io"
PLATFORM_API_VERSION = "v1"
PLATFORM_PLURAL = "platforms"

LOCK_KEY = "neu.ro/lock-key"
LOCK_EXPIRES_AT = "neu.ro/lock-expires-at"


class PlatformPhase(str, Enum):
    PENDING = "Pending"
    DEPLOYING = "Deploying"
    DELETING = "Deleting"
    DEPLOYED = "Deployed"
    FAILED = "Failed"


class PlatformConditionType(str, Enum):
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


class Metadata:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    @property
    def annotations(self) -> dict[str, Any]:
        if "annotations" not in self._payload:
            self._payload["annotations"] = {}
        return self._payload["annotations"]


class Node(dict[str, Any]):
    @property
    def container_runtime(self) -> str:
        version = self["status"]["nodeInfo"]["containerRuntimeVersion"]
        end = version.find("://")
        return version[0:end]


class Service(dict[str, Any]):
    @property
    def cluster_ip(self) -> str:
        return self["spec"]["clusterIP"]

    @property
    def load_balancer_host(self) -> str:
        return self["status"]["loadBalancer"]["ingress"][0]["hostname"]


class Secret(dict[str, Any]):
    @property
    def metadata(self) -> Metadata:
        return Metadata(self["metadata"])


class KubeClient:
    def __init__(
        self,
        config: KubeConfig,
        trace_configs: list[aiohttp.TraceConfig] | None = None,
    ) -> None:
        self._config = config
        self._token = (
            config.read_auth_token_from_path() if config.auth_token_path else None
        )
        self._trace_configs = trace_configs
        self._session: aiohttp.ClientSession | None = None
        self._token_updater_task: asyncio.Task[None] | None = None
        self._endpoints = Endpoints(config.url)

    @property
    def _is_ssl(self) -> bool:
        return self._config.url.scheme == "https"

    def _create_ssl_context(self) -> ssl.SSLContext | bool:
        if not self._is_ssl:
            return True
        assert self._config.cert_authority_path
        ssl_context = ssl.create_default_context(
            cafile=self._config.cert_authority_path
        )
        if self._config.auth_type == KubeClientAuthType.CERTIFICATE:
            assert self._config.auth_cert_path
            assert self._config.auth_cert_key_path
            ssl_context.load_cert_chain(
                str(self._config.auth_cert_path), str(self._config.auth_cert_key_path)
            )
        return ssl_context

    async def __aenter__(self) -> Self:
        await self._init()
        return self

    async def _init(self) -> None:
        if self._config.auth_token_path:
            self._token_updater_task = asyncio.create_task(self._start_token_updater())
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
        )

    async def _start_token_updater(self) -> None:
        while True:
            await asyncio.sleep(max(10, self._config.auth_token_exp_ts - 60 - time()))
            try:
                token = self._config.read_auth_token_from_path()
                if token != self._token:
                    self._token = token
                    logger.info("Kube token was refreshed")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Failed to update kube token: %s", exc)

    async def __aexit__(self, *args: object, **kwargs: Any) -> None:
        await self.close()

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None
        if self._token_updater_task:
            self._token_updater_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._token_updater_task
            self._token_updater_task = None

    def _create_headers(self, headers: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = dict(headers) if headers else {}
        if self._config.auth_type == KubeClientAuthType.TOKEN and self._token:
            headers["Authorization"] = "Bearer " + self._token
        return headers

    async def _request(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        headers = self._create_headers(kwargs.pop("headers", None))
        assert self._session, "client is not initialized"
        async with self._session.request(*args, headers=headers, **kwargs) as response:
            response.raise_for_status()
            return await response.json()

    async def get_node(self, name: str) -> Node:
        payload = await self._request(method="get", url=self._endpoints.node(name))
        return Node(payload)

    async def create_namespace(self, name: str) -> None:
        await self._request(
            method="post",
            url=self._endpoints.namespaces,
            json={"metadata": {"name": name}},
        )

    async def delete_namespace(self, name: str) -> None:
        await self._request(
            method="delete",
            url=self._endpoints.namespace(name),
            json={"propagationPolicy": "Background"},
        )

    async def get_service(self, namespace: str, name: str) -> Service:
        payload = await self._request(
            method="get",
            url=self._endpoints.service(namespace, name),
        )
        return Service(payload)

    async def get_service_account(self, namespace: str, name: str) -> dict[str, Any]:
        return await self._request(
            method="get",
            url=self._endpoints.service_account(namespace, name),
        )

    async def update_service_account(
        self,
        namespace: str,
        name: str,
        *,
        annotations: dict[str, str] | None = None,
        image_pull_secrets: Iterable[str] = (),
    ) -> None:
        data: dict[str, Any] = {}
        if annotations:
            data["metadata"] = {"annotations": annotations}
        if image_pull_secrets:
            data["imagePullSecrets"] = [{"name": name} for name in image_pull_secrets]
        if not data:
            return
        await self._request(
            method="patch",
            url=self._endpoints.service_account(namespace, name),
            headers={"Content-Type": "application/merge-patch+json"},
            data=json.dumps(data),
        )

    async def create_secret(self, namespace: str, payload: dict[str, Any]) -> None:
        await self._request(
            method="post",
            url=self._endpoints.secrets(namespace),
            json=payload,
        )

    async def update_secret(
        self, namespace: str, name: str, payload: dict[str, Any]
    ) -> None:
        await self._request(
            method="put",
            url=self._endpoints.secret(namespace, name),
            json=payload,
        )

    async def delete_secret(self, namespace: str, name: str) -> None:
        await self._request(
            method="delete",
            url=self._endpoints.secret(namespace, name),
        )

    async def get_secret(self, namespace: str, name: str) -> Secret:
        payload = await self._request(
            method="get",
            url=self._endpoints.secret(namespace, name),
        )
        return Secret(self._decode_secret_data(payload))

    def _encode_secret_data(self, secret: dict[str, Any]) -> dict[str, Any]:
        secret = dict(**secret)
        encoded_data: dict[str, str] = {}
        for key, value in secret.get("data", {}).items():
            encoded_data[key] = b64encode(value.encode("utf-8")).decode("utf-8")
        if encoded_data:
            secret["data"] = encoded_data
        return secret

    def _decode_secret_data(self, secret: dict[str, Any]) -> dict[str, Any]:
        secret = dict(**secret)
        decoded_data: dict[str, str] = {}
        for key, value in secret.get("data", {}).items():
            decoded_data[key] = b64decode(value).decode("utf-8")
        if decoded_data:
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
        payload = await self._request(
            method="get",
            url=self._endpoints.pods(namespace).with_query(**query),
        )
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
        await self._request(
            method="post",
            url=self._endpoints.platforms(namespace=namespace),
            json=payload,
        )

    async def delete_platform(self, namespace: str, name: str) -> None:
        await self._request(
            method="delete", url=self._endpoints.platform(namespace, name)
        )

    async def get_platform_status(
        self, namespace: str, name: str
    ) -> dict[str, Any] | None:
        payload = await self._request(
            method="get",
            url=self._endpoints.platform(namespace, name) / "status",
        )
        if "status" not in payload:
            return None
        return payload["status"]

    async def update_platform_status(
        self, namespace: str, name: str, payload: dict[str, Any]
    ) -> None:
        await self._request(
            method="patch",
            url=self._endpoints.platform(namespace, name) / "status",
            headers={"Content-Type": "application/merge-patch+json"},
            data=json.dumps({"status": payload}),
        )

    async def acquire_lock(
        self,
        namespace: str,
        name: str,
        lock_key: str,
        *,
        ttl_s: float = 15 * 60,
        sleep_s: float = 0.1,
    ) -> None:
        while True:
            try:
                resource = await self.get_secret(namespace, name)
                expires_at = datetime.now(UTC) + timedelta(seconds=ttl_s)
                annotations = resource.metadata.annotations
                old_lock_key = annotations.get(LOCK_KEY)
                if (
                    old_lock_key is None
                    or old_lock_key == lock_key
                    or datetime.fromisoformat(annotations[LOCK_EXPIRES_AT])
                    <= datetime.now(UTC)
                ):
                    annotations[LOCK_KEY] = lock_key
                    annotations[LOCK_EXPIRES_AT] = expires_at.isoformat()
                    await self.update_secret(namespace, name, resource)
                    logger.debug(
                        "Lock %r acquired, expires at %r",
                        lock_key,
                        expires_at.isoformat(),
                    )
                    return
            except aiohttp.ClientResponseError as ex:
                if ex.status == 409:
                    logger.debug(
                        "Failed to acquire lock %r: resource modified", lock_key
                    )
                else:
                    logger.debug(
                        "Failed to acquire lock %r: unexpected error", lock_key
                    )
                    raise
            logger.debug("Waiting for %rs until next attempt", sleep_s)
            await asyncio.sleep(sleep_s)

    async def release_lock(self, namespace: str, name: str, lock_key: str) -> None:
        while True:
            try:
                resource = await self.get_secret(namespace, name)
                annotations = resource.metadata.annotations
                old_lock_key = annotations.get(LOCK_KEY)
                if old_lock_key is None or lock_key == old_lock_key:
                    annotations.pop(LOCK_KEY, None)
                    annotations.pop(LOCK_EXPIRES_AT, None)
                    await self.update_secret(namespace, name, resource)
                    logger.debug("Lock %r released", lock_key)
                return
            except aiohttp.ClientResponseError as ex:
                if ex.status == 409:
                    logger.debug(
                        "Failed to release lock %r: resource modified", lock_key
                    )
                else:
                    logger.debug(
                        "Failed to release lock %r: unexpected error", lock_key
                    )
                    raise

    @asynccontextmanager
    async def lock(
        self,
        namespace: str,
        name: str,
        lock_key: str,
        *,
        ttl_s: float = 15 * 60,
        sleep_s: float = 0.1,
    ) -> AsyncIterator[None]:
        try:
            await self.acquire_lock(
                namespace, name, lock_key, ttl_s=ttl_s, sleep_s=sleep_s
            )
            yield
        finally:
            await asyncio.shield(self.release_lock(namespace, name, lock_key))


class PlatformCondition(dict[str, Any]):
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

    def _deserialize(self, payload: dict[str, Any]) -> PlatformStatus:
        status = {
            "phase": payload["phase"],
            "retries": payload["retries"],
            "conditions": self._deserialize_conditions(payload["conditions"]),
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
        return datetime.now(UTC).replace(microsecond=0).isoformat()

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
