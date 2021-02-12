import asyncio
import gzip
import json
from typing import Any, Awaitable, Callable, Dict, Optional
from unittest import mock

import pytest
from aiohttp import ClientSession, web
from yarl import URL

from platform_operator.certificate_store import CertificateStore
from platform_operator.consul_client import ConsulClient
from platform_operator.models import Certificate


class CertificateStoreApp:
    def __init__(self, account: Optional[Dict[str, Any]] = None) -> None:
        self.web_app = web.Application()
        self._account = account

        self.web_app.router.add_get(
            "/v1/kv/traefik/acme/account/object", self.get_account
        )

    async def get_account(self, request: web.Request) -> web.Response:
        if self._account:
            data = gzip.compress(json.dumps(self._account).encode())
            return web.Response(body=data)
        return web.Response(status=web.HTTPNotFound.status_code)


class TestCertificateStore:
    @pytest.fixture
    def consul_client(self) -> ConsulClient:
        return ConsulClient(URL())

    @pytest.fixture
    def store(self, consul_client: ConsulClient) -> CertificateStore:
        return CertificateStore(consul_client)

    async def test_no_certificate(
        self,
        aiohttp_client: Callable[[web.Application], Awaitable[ClientSession]],
        consul_client: ConsulClient,
        store: CertificateStore,
    ) -> None:
        app = CertificateStoreApp()
        client = await aiohttp_client(app.web_app)

        with mock.patch.object(consul_client, "_client", new=client):
            cert = await store.get_certificate()

            assert cert is None

            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(store.wait_till_certificate_created(), 1)

    async def test_certificate_not_ready(
        self,
        aiohttp_client: Callable[[web.Application], Awaitable[ClientSession]],
        consul_client: ConsulClient,
        store: CertificateStore,
    ) -> None:
        app = CertificateStoreApp({"DomainsCertificate": {"Certs": None}})
        client = await aiohttp_client(app.web_app)

        with mock.patch.object(consul_client, "_client", new=client):
            cert = await store.get_certificate()

            assert cert is None

            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(store.wait_till_certificate_created(), 1)

    async def test_certificate(
        self,
        aiohttp_client: Callable[[web.Application], Awaitable[ClientSession]],
        consul_client: ConsulClient,
        store: CertificateStore,
    ) -> None:
        app = CertificateStoreApp(
            {
                "DomainsCertificate": {
                    "Certs": [
                        {
                            "Certificate": {
                                "PrivateKey": "UHJpdmF0ZUtleQ==",
                                "Certificate": "Q2VydGlmaWNhdGU=",
                            }
                        }
                    ]
                }
            }
        )
        client = await aiohttp_client(app.web_app)

        with mock.patch.object(consul_client, "_client", new=client):
            cert = await store.get_certificate()

            assert cert == Certificate(
                private_key="PrivateKey",
                certificate="Certificate",
            )

            await store.wait_till_certificate_created()
