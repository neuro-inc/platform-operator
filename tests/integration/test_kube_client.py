from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import aiohttp
import aiohttp.web
import kopf
import pytest
from yarl import URL

from platform_operator.kube_client import (
    LOCK_EXPIRES_AT,
    LOCK_KEY,
    KubeClient,
    KubeClientAuthType,
)
from platform_operator.models import KubeConfig

from .conftest import create_local_app_server


class TestKubeClientTokenUpdater:
    @pytest.fixture
    async def kube_app(self) -> aiohttp.web.Application:
        async def _get_pods(request: aiohttp.web.Request) -> aiohttp.web.Response:
            auth = request.headers["Authorization"]
            token = auth.split()[-1]
            app["token"]["value"] = token
            return aiohttp.web.json_response({"kind": "PodList", "items": []})

        app = aiohttp.web.Application()
        app["token"] = {"value": ""}
        app.router.add_routes(
            [aiohttp.web.get("/api/v1/namespaces/default/pods", _get_pods)]
        )
        return app

    @pytest.fixture
    async def kube_server(
        self, kube_app: aiohttp.web.Application, unused_tcp_port_factory: Any
    ) -> AsyncIterator[str]:
        async with create_local_app_server(
            kube_app, port=unused_tcp_port_factory()
        ) as address:
            yield f"http://{address.host}:{address.port}"

    @pytest.fixture
    def kube_token_path(self) -> Iterator[str]:
        _, path = tempfile.mkstemp()
        Path(path).write_text("token-1")
        yield path
        os.remove(path)

    @pytest.fixture
    async def kube_client(
        self, kube_server: str, kube_token_path: str
    ) -> AsyncIterator[KubeClient]:
        async with KubeClient(
            config=KubeConfig(
                version="1.25",
                url=URL(kube_server),
                auth_type=KubeClientAuthType.TOKEN,
                auth_token_path=Path(kube_token_path),
                auth_token_update_interval_s=1,
            )
        ) as client:
            yield client

    async def test_token_periodically_updated(
        self,
        kube_app: aiohttp.web.Application,
        kube_client: KubeClient,
        kube_token_path: str,
    ) -> None:
        await kube_client.get_pods("default")
        assert kube_app["token"]["value"] == "token-1"

        Path(kube_token_path).write_text("token-2")
        await asyncio.sleep(2)

        await kube_client.get_pods("default")
        assert kube_app["token"]["value"] == "token-2"


class TestKubeClient:
    @pytest.fixture
    async def platform(
        self,
        kube_client: KubeClient,
        kube_namespace: str,
        gcp_platform_body: kopf.Body,
    ) -> AsyncIterator[dict[str, Any]]:
        payload = dict(**gcp_platform_body)
        await kube_client.create_platform(kube_namespace, payload)
        yield payload
        await kube_client.delete_platform(
            namespace=kube_namespace, name=payload["metadata"]["name"]
        )

    async def test_get_service(self, kube_client: KubeClient) -> None:
        service = await kube_client.get_service(namespace="default", name="kubernetes")

        assert service["metadata"]["name"] == "kubernetes"

    async def test_get_unknown_service__raises_error(
        self, kube_client: KubeClient
    ) -> None:
        with pytest.raises(aiohttp.ClientError):
            await kube_client.get_service(namespace="default", name="unknown")

    async def test_get_service_account_and_secret(
        self, kube_client: KubeClient
    ) -> None:
        service_account = await kube_client.get_service_account("default", "default")

        assert service_account["metadata"]["name"] == "default"

        secret_name = service_account["secrets"][0]["name"]
        secret = await kube_client.get_secret(namespace="default", name=secret_name)

        assert secret["metadata"]["name"] == secret_name
        assert secret["data"]["namespace"] == "default"

    async def test_update_service_account(self, kube_client: KubeClient) -> None:
        for _ in range(2):
            # Should be idempotent
            await kube_client.update_service_account(
                "default",
                "default",
                annotations={"role-arn": "neuro"},
                image_pull_secrets=["secret"],
            )

        service_account = await kube_client.get_service_account("default", "default")

        assert service_account["metadata"]["annotations"] == {"role-arn": "neuro"}
        assert service_account["imagePullSecrets"] == [{"name": "secret"}]

    async def test_get_unknown_secret__raises_error(
        self, kube_client: KubeClient
    ) -> None:
        with pytest.raises(aiohttp.ClientError):
            await kube_client.get_secret(namespace="default", name="unknown")

    async def test_get_pods(self, kube_client: KubeClient) -> None:
        result = await kube_client.get_pods(namespace="kube-system")

        assert len(result) > 1

    async def test_get_pods_with_limit(self, kube_client: KubeClient) -> None:
        result = await kube_client.get_pods(namespace="kube-system", limit=1)

        assert len(result) == 1

    async def test_get_pods_with_label_selector(self, kube_client: KubeClient) -> None:
        pods = await kube_client.get_pods(
            namespace="kube-system", label_selector={"k8s-app": "kube-proxy"}
        )

        for pod in pods:
            assert pod["metadata"]["name"].startswith("kube-proxy")

    async def test_get_pods_in_unknown_namespace(self, kube_client: KubeClient) -> None:
        result = await kube_client.get_pods(namespace="unknown")

        assert result == []

    async def test_wait_till_pods_deleted(
        self, kube_client: KubeClient, kube_namespace: str
    ) -> None:
        await kube_client.wait_till_pods_deleted(namespace=kube_namespace)

    async def test_wait_till_pods_deleted_forever(
        self, kube_client: KubeClient
    ) -> None:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                kube_client.wait_till_pods_deleted(
                    namespace="kube-system", interval_secs=1
                ),
                2,
            )

    async def test_platform_status(
        self,
        kube_client: KubeClient,
        kube_namespace: str,
        platform: dict[str, Any],
    ) -> None:
        name = platform["metadata"]["name"]
        result = await kube_client.get_platform_status(
            namespace=kube_namespace, name=name
        )

        assert result is None

        await kube_client.update_platform_status(
            namespace=kube_namespace, name=name, payload={"phase": "Deployed"}
        )
        result = await kube_client.get_platform_status(
            namespace=kube_namespace, name=name
        )

        assert result == {"phase": "Deployed"}

    @pytest.fixture
    async def lock_secret(self, kube_client: KubeClient) -> AsyncIterator[str]:
        try:
            await kube_client.create_secret("default", {"metadata": {"name": "lock"}})
            yield "lock"
        finally:
            await kube_client.delete_secret("default", "lock")

    async def test_lock(self, kube_client: KubeClient, lock_secret: str) -> None:
        messages = []

        async def lock(key: str, delay: float | None = None) -> None:
            if delay is not None:
                await asyncio.sleep(delay)

            async with kube_client.lock("default", lock_secret, key, ttl_s=5):
                messages.append(f"start {key}")
                await asyncio.sleep(0.5)
                messages.append(f"end {key}")

        tasks = [
            asyncio.create_task(lock("1")),
            asyncio.create_task(lock("2", delay=0.1)),
        ]
        await asyncio.wait(tasks)

        assert messages == ["start 1", "end 1", "start 2", "end 2"]

    async def test_lock_released_on_error(
        self, kube_client: KubeClient, lock_secret: str
    ) -> None:
        try:
            async with kube_client.lock("default", lock_secret, "test", ttl_s=5):
                raise asyncio.CancelledError()
        except asyncio.CancelledError:
            pass
        secret = await kube_client.get_secret("default", lock_secret)
        assert LOCK_KEY not in secret.metadata.annotations
        assert LOCK_EXPIRES_AT not in secret.metadata.annotations

    async def test_lock_reenter(
        self, kube_client: KubeClient, lock_secret: str
    ) -> None:
        async with kube_client.lock("default", lock_secret, "test", ttl_s=1):
            async with kube_client.lock("default", lock_secret, "test", ttl_s=1):
                pass
            secret = await kube_client.get_secret("default", lock_secret)
            assert LOCK_KEY not in secret.metadata.annotations
            assert LOCK_EXPIRES_AT not in secret.metadata.annotations

    async def test_lock_expired(
        self, kube_client: KubeClient, lock_secret: str
    ) -> None:
        await kube_client.acquire_lock("default", lock_secret, "test1", ttl_s=0.5)

        await asyncio.sleep(1)

        async with kube_client.lock("default", lock_secret, "test2", ttl_s=0.5):
            secret = await kube_client.get_secret("default", lock_secret)
            assert secret.metadata.annotations[LOCK_KEY] == "test2"
            assert LOCK_EXPIRES_AT in secret.metadata.annotations

    async def test_lock_not_found(self, kube_client: KubeClient) -> None:
        with pytest.raises(aiohttp.ClientError):
            async with kube_client.lock("default", "unknown", "test", ttl_s=0.5):
                pass

    async def test_release_other_lock(
        self, kube_client: KubeClient, lock_secret: str
    ) -> None:
        async with kube_client.lock("default", lock_secret, "test", ttl_s=0.5):
            await kube_client.release_lock("default", lock_secret, "test_other")

            secret = await kube_client.get_secret("default", lock_secret)
            assert secret.metadata.annotations[LOCK_KEY] == "test"
            assert LOCK_EXPIRES_AT in secret.metadata.annotations

    async def test_release_not_acquired_lock(
        self, kube_client: KubeClient, lock_secret: str
    ) -> None:
        secret = await kube_client.get_secret("default", lock_secret)
        assert LOCK_KEY not in secret.metadata.annotations
        assert LOCK_EXPIRES_AT not in secret.metadata.annotations

        await kube_client.release_lock("default", lock_secret, "test")
