import asyncio
import gzip
import json
import logging
from base64 import b64decode
from types import SimpleNamespace
from typing import Any, Dict, Optional

import aiohttp
from aiohttp.web import HTTPNotFound
from yarl import URL

from .models import Certificate


logger = logging.getLogger(__name__)


class CertificateStore:
    def __init__(self, consul_url: URL) -> None:
        self._consul_url = consul_url / "v1/kv"
        self._session: Optional[aiohttp.ClientSession] = None

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

    async def __aenter__(self) -> "CertificateStore":
        trace_config = aiohttp.TraceConfig()
        trace_config.on_request_start.append(self._on_request_start)  # type: ignore
        trace_config.on_request_end.append(self._on_request_end)  # type: ignore
        self._session = aiohttp.ClientSession(trace_configs=[trace_config])
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
        await self.close()

    async def close(self) -> None:
        assert self._session
        await self._session.close()

    async def _get_acme_account(self) -> Optional[Dict[str, Any]]:
        assert self._session
        async with self._session.get(
            self._consul_url / "traefik/acme/account/object",
        ) as response:
            if response.status == HTTPNotFound.status_code:
                return None
            response.raise_for_status()
            payload = await response.json()
            value = payload[0]["Value"]
            value_decompressed = gzip.decompress(b64decode(value.encode()))
            return json.loads(value_decompressed.decode())

    async def get_certificate(self) -> Optional[Certificate]:
        account = await self._get_acme_account()
        if not account:
            return None

        certs = account.get("DomainsCertificate", {}).get("Certs")
        if not certs:
            return None
        cert = certs[0].get("Certificate")
        if not cert:
            return None

        return Certificate(
            private_key=b64decode(cert["PrivateKey"].encode()).decode(),
            certificate=b64decode(cert["Certificate"].encode()).decode(),
        )

    async def wait_till_certificate_created(self, interval_secs: int = 5) -> None:
        while True:
            cert = await self.get_certificate()
            if cert:
                break
            await asyncio.sleep(interval_secs)
