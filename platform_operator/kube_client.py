import logging
import ssl
from base64 import b64decode
from types import SimpleNamespace
from typing import Any, Dict, Optional

import aiohttp
from yarl import URL

from .models import KubeClientAuthType, KubeConfig


logger = logging.getLogger(__name__)


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
                "Received %s %s %s", params.method, params.response.status, params.url,
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
        trace_config.on_request_start.append(self._on_request_start)  # type: ignore
        trace_config.on_request_end.append(self._on_request_end)  # type: ignore
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
            self._get_namespace_url(), json={"metadata": {"name": name}},
        ) as response:
            response.raise_for_status()

    async def delete_namespace(self, name: str) -> None:
        assert self._session
        async with self._session.delete(
            self._get_namespace_url(name), json={"propagationPolicy": "Background"},
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
