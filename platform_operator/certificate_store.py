from __future__ import annotations

import asyncio
import gzip
import json
import logging
from base64 import b64decode
from typing import Any

from aiohttp.client import ClientResponseError
from aiohttp.client_exceptions import ClientError
from aiohttp.web import HTTPNotFound

from platform_operator.consul_client import ConsulClient

from .models import Certificate

logger = logging.getLogger(__name__)


class CertificateStore:
    def __init__(self, consul_client: ConsulClient) -> None:
        self._consul_client = consul_client

    async def _get_acme_account(self) -> dict[str, Any] | None:
        try:
            value = await self._consul_client.get_key(
                "traefik/acme/account/object", raw=True
            )
        except ClientResponseError as exc:
            if exc.status != HTTPNotFound.status_code:
                logger.warning(
                    "Error while trying to get ACME account from consul", exc_info=exc
                )
            return None
        assert isinstance(value, bytes)
        value_decompressed = gzip.decompress(value)
        return json.loads(value_decompressed.decode())

    async def get_certificate(self) -> Certificate | None:
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

    async def wait_till_certificate_created(self, interval_s: int = 5) -> None:
        while True:
            try:
                cert = await self.get_certificate()
            except ClientError as exc:
                logger.warning("Certificate request failed", exc_info=exc)
            else:
                if cert:
                    break
            await asyncio.sleep(interval_s)
