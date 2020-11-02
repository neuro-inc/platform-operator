import asyncio
import json
import logging
import ssl
from base64 import b64decode
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from types import SimpleNamespace
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence

import aiohttp
from yarl import URL

from .models import KubeClientAuthType, KubeConfig


logger = logging.getLogger(__name__)

PLATFORM_GROUP = "neuromation.io"
PLATFORM_API_VERSION = "v1"
PLATFORM_PLURAL = "platforms"


class PlatformPhase(str, Enum):
    DEPLOYING = "Deploying"
    DELETING = "Deleting"
    DEPLOYED = "Deployed"
    FAILED = "Failed"


class PlatformConditionType(str, Enum):
    OBS_CSI_DRIVER_DEPLOYED = "ObsCsiDriverDeployed"
    NFS_SERVER_DEPLOYED = "NfsServerDeployed"
    PLATFORM_DEPLOYED = "PlatformDeployed"
    CERTIFICATE_CREATED = "CertificateCreated"
    DNS_CONFIGURED = "DnsConfigured"
    CLUSTER_CONFIGURED = "ClusterConfigured"


class PlatformConditionStatus(str, Enum):
    TRUE = "True"
    FALSE = "False"
    # The state is unknown, platform deployment might have succeeded
    # or failed but we don't know because timeout have occurred
    UNKNOWN = "Unknown"


class KubeClient:
    def __init__(self, config: KubeConfig) -> None:
        self._config = config
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def _is_ssl(self) -> bool:
        return self._config.url.scheme == "https"

    def _create_ssl_context(self) -> Optional[ssl.SSLContext]:
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

    async def _on_request_start(
        self,
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceRequestStartParams,
    ) -> None:
        logger.info("Sending %s %s", params.method, params.url)

    async def _on_request_end(
        self,
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceRequestEndParams,
    ) -> None:
        if 400 <= params.response.status:
            logger.warning(
                "Received %s %s %s\n%s",
                params.method,
                params.response.status,
                params.url,
                await params.response.text(),
            )
        else:
            logger.info(
                "Received %s %s %s",
                params.method,
                params.response.status,
                params.url,
            )

    async def __aenter__(self) -> "KubeClient":
        if self._config.auth_type == KubeClientAuthType.TOKEN:
            assert self._config.auth_token or self._config.auth_token_path
            if self._config.auth_token:
                headers = {"Authorization": "Bearer " + self._config.auth_token}
            if self._config.auth_token_path:
                headers = {
                    "Authorization": "Bearer "
                    + self._config.auth_token_path.read_text()
                }
        else:
            headers = {}
        connector = aiohttp.TCPConnector(
            limit=self._config.conn_pool_size, ssl=self._create_ssl_context()
        )
        timeout = aiohttp.ClientTimeout(
            connect=self._config.conn_timeout_s, total=self._config.read_timeout_s
        )
        trace_config = aiohttp.TraceConfig()
        trace_config.on_request_start.append(self._on_request_start)
        trace_config.on_request_end.append(self._on_request_end)
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            trace_configs=[trace_config],
            headers=headers,
        )
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
        assert self._session
        await self._session.close()
        self._session = None

    def _get_namespace_url(self, namespace: str = "") -> URL:
        base_url = self._config.url / "api/v1/namespaces"
        return base_url / namespace if namespace else base_url

    async def create_namespace(self, name: str) -> None:
        assert self._session
        async with self._session.post(
            self._get_namespace_url(),
            json={"metadata": {"name": name}},
        ) as response:
            response.raise_for_status()

    async def delete_namespace(self, name: str) -> None:
        assert self._session
        async with self._session.delete(
            self._get_namespace_url(name),
            json={"propagationPolicy": "Background"},
        ) as response:
            response.raise_for_status()

    async def get_service(self, namespace: str, name: str) -> Dict[str, Any]:
        assert self._session
        async with self._session.get(
            self._get_namespace_url(namespace) / "services" / name
        ) as response:
            response.raise_for_status()
            payload = await response.json()
            return payload

    async def get_service_account(self, namespace: str, name: str) -> Dict[str, Any]:
        assert self._session
        async with self._session.get(
            self._get_namespace_url(namespace) / "serviceaccounts" / name
        ) as response:
            response.raise_for_status()
            payload = await response.json()
            return payload

    async def get_secret(self, namespace: str, name: str) -> Dict[str, Any]:
        assert self._session
        async with self._session.get(
            self._get_namespace_url(namespace) / "secrets" / name
        ) as response:
            response.raise_for_status()
            payload = await response.json()
            return self._decode_secret_data(payload)

    def _decode_secret_data(self, secret: Dict[str, Any]) -> Dict[str, Any]:
        secret = dict(**secret)
        decoded_data: Dict[str, str] = {}
        for key, value in secret["data"].items():
            decoded_data[key] = b64decode(value.encode("utf-8")).decode("utf-8")
        secret["data"] = decoded_data
        return secret

    async def get_pods(
        self,
        namespace: str,
        label_selector: Optional[Dict[str, str]] = None,
        limit: int = 100,
    ) -> Sequence[Dict[str, Any]]:
        assert limit
        query = {"limit": str(limit)}
        if label_selector:
            query["labelSelector"] = ",".join(
                f"{key}={value}" for key, value in label_selector.items()
            )
        assert self._session
        async with self._session.get(
            (self._get_namespace_url(namespace) / "pods").with_query(**query)
        ) as response:
            response.raise_for_status()
            payload = await response.json()
            return payload["items"]

    async def wait_till_pods_deleted(
        self,
        namespace: str,
        label_selector: Optional[Dict[str, str]] = None,
        interval_secs: int = 5,
    ) -> None:
        while True:
            payload = await self.get_pods(namespace, label_selector, 1)
            if not payload:
                break
            await asyncio.sleep(interval_secs)

    def _get_platform_url(self, namespace: str, name: str = "") -> URL:
        base_url = (
            self._config.url
            / f"apis/{PLATFORM_GROUP}/{PLATFORM_API_VERSION}/namespaces"
            / f"{namespace}/{PLATFORM_PLURAL}"
        )
        return base_url / name if name else base_url

    async def create_platform(self, namespace: str, payload: Dict[str, Any]) -> None:
        assert self._session
        async with self._session.post(
            self._get_platform_url(namespace=namespace), json=payload
        ) as response:
            response.raise_for_status()

    async def delete_platform(self, namespace: str, name: str) -> None:
        assert self._session
        async with self._session.delete(
            self._get_platform_url(namespace=namespace, name=name)
        ) as response:
            response.raise_for_status()

    async def get_platform_status(
        self, namespace: str, name: str
    ) -> Optional[Dict[str, Any]]:
        assert self._session
        async with self._session.get(
            self._get_platform_url(namespace=namespace, name=name) / "status"
        ) as response:
            response.raise_for_status()
            payload = await response.json()
            if "status" not in payload:
                return None
            status_payload = payload["status"]
            return status_payload

    async def update_platform_status(
        self, namespace: str, name: str, payload: Dict[str, Any]
    ) -> None:
        assert self._session
        async with self._session.patch(
            self._get_platform_url(namespace=namespace, name=name) / "status",
            headers={"Content-Type": "application/merge-patch+json"},
            data=json.dumps({"status": payload}),
        ) as response:
            response.raise_for_status()


class PlatformCondition(Dict[str, Any]):
    def __init__(self, payload: Dict[str, Any]) -> None:
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


class PlatformStatus(Dict[str, Any]):
    def __init__(self, payload: Dict[str, Any]) -> None:
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
    def conditions(self) -> List[PlatformCondition]:
        return self["conditions"]

    @conditions.setter
    def conditions(self, value: List[PlatformCondition]) -> None:
        self["conditions"] = value


class PlatformStatusManager:
    def __init__(
        self,
        kube_client: KubeClient,
        namespace: str,
        name: str,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._kube_client = kube_client
        self._namespace = namespace
        self._name = name
        self._logger = logger or logging.getLogger(__name__)
        self._status: Optional[PlatformStatus] = None

    async def _load(self) -> None:
        if self._status:
            return
        payload = await self._kube_client.get_platform_status(
            namespace=self._namespace, name=self._name
        )
        payload = payload or {"conditions": []}
        self._status = PlatformStatus(payload)

    async def _save(self) -> None:
        assert self._status
        await self._kube_client.update_platform_status(
            namespace=self._namespace, name=self._name, payload=self._status
        )

    def _now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def is_condition_satisfied(self, type: PlatformConditionType) -> bool:
        assert self._status
        for condition in self._status.conditions:
            if condition["type"] == type.value:
                return condition["status"] == PlatformConditionStatus.TRUE.value
        return False

    async def start_deployment(self, retry: int = 0) -> None:
        await self._load()
        assert self._status
        self._status.phase = PlatformPhase.DEPLOYING.value
        self._status.retries = retry
        if retry == 0:
            self._status.conditions = []
        await self._save()

    async def complete_deployment(self) -> None:
        await self._load()
        assert self._status
        self._status.phase = PlatformPhase.DEPLOYED.value
        await self._save()

    async def fail_deployment(self) -> None:
        await self._load()
        assert self._status
        self._status.phase = PlatformPhase.FAILED.value
        if self._status.conditions:
            condition = self._status.conditions[-1]
            if condition["status"] == PlatformConditionStatus.FALSE.value:
                condition["status"] = PlatformConditionStatus.UNKNOWN.value
                condition["lastTransitionTime"] = self._now()
        await self._save()

    async def start_deletion(self) -> None:
        await self._load()
        assert self._status
        self._status.phase = PlatformPhase.DELETING.value
        await self._save()

    @asynccontextmanager
    async def transition(self, type: PlatformConditionType) -> AsyncIterator[None]:
        assert self._status
        logger.info("Started transition to %s condition", type.value)
        self._status.conditions.append(PlatformCondition({}))
        self._status.conditions[-1].type = type.value
        self._status.conditions[-1].status = PlatformConditionStatus.FALSE.value
        self._status.conditions[-1].last_transition_time = self._now()
        await self._save()
        yield
        self._status.conditions[-1].status = PlatformConditionStatus.TRUE.value
        self._status.conditions[-1].last_transition_time = self._now()
        await self._save()
        logger.info("Transition to %s succeeded", type.value)
