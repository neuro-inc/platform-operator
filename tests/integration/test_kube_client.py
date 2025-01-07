from __future__ import annotations

import asyncio
import json
from base64 import urlsafe_b64encode
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from time import time
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
    def jwt_kube_token_with_exp_factory(self) -> Callable[[int], str]:
        def _create_jwt_kube_token_with_exp(exp: int) -> str:
            payload = {"exp": exp}
            payload_encoded = (
                urlsafe_b64encode(json.dumps(payload).encode("utf-8"))
                .rstrip(b"=")
                .decode("utf-8")
            )
            return f"header.{payload_encoded}.signature"

        return _create_jwt_kube_token_with_exp

    @pytest.fixture
    def kube_auth_token(
        self, jwt_kube_token_with_exp_factory: Callable[[int], str]
    ) -> str:
        return jwt_kube_token_with_exp_factory(int(time()) + 2)

    @pytest.fixture
    def kube_auth_token_path(self, kube_auth_token: str, tmp_path: Path) -> Path:
        token_file = tmp_path / "token"
        token_file.write_text(kube_auth_token)
        return token_file

    @pytest.fixture
    async def kube_client(
        self, kube_server: str, kube_auth_token_path: Path
    ) -> AsyncIterator[KubeClient]:
        async with KubeClient(
            config=KubeConfig(
                version="1.25",
                url=URL(kube_server),
                auth_type=KubeClientAuthType.TOKEN,
                auth_token_path=kube_auth_token_path,
            )
        ) as client:
            yield client

    async def test_auth_token_exp_ts_value_error(self, kube_server: str) -> None:
        kube_config = KubeConfig(
            version="1.25",
            url=URL(kube_server),
            auth_type=KubeClientAuthType.TOKEN,
            auth_token_path=None,
        )
        with pytest.raises(ValueError, match="auth_token_path must be set"):
            _ = kube_config.read_auth_token_from_path()

        with pytest.raises(ValueError, match="auth_token_path must be set"):
            _ = kube_config.auth_token_exp_ts

    async def test_read_auth_token_from_path(
        self,
        kube_client: KubeClient,
        jwt_kube_token_with_exp_factory: Callable[[int], str],
    ) -> None:
        assert kube_client._config.auth_token_path

        old_token = kube_client._config.read_auth_token_from_path()

        new_token = jwt_kube_token_with_exp_factory(int(time()) + 3)
        kube_client._config.auth_token_path.write_text(new_token)

        assert kube_client._config.read_auth_token_from_path() == new_token
        assert kube_client._config.read_auth_token_from_path() != old_token

    async def test_token_periodically_updated(
        self,
        kube_app: aiohttp.web.Application,
        kube_client: KubeClient,
        jwt_kube_token_with_exp_factory: Callable[[int], str],
    ) -> None:
        assert kube_client._config.auth_token_path

        await kube_client.get_pods("default")
        assert (
            kube_app["token"]["value"]
            == kube_client._config.read_auth_token_from_path()
        )

        new_token = jwt_kube_token_with_exp_factory(int(time()) + 5)
        kube_client._config.auth_token_path.write_text(new_token)

        await asyncio.sleep(11)

        await kube_client.get_pods("default")
        assert kube_app["token"]["value"] == new_token


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
