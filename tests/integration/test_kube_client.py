from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import aiohttp
import kopf
import pytest

from platform_operator.kube_client import LOCK_EXPIRES_AT, LOCK_KEY, KubeClient


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

    async def test_update_service_account_image_pull_secrets(
        self, kube_client: KubeClient
    ) -> None:
        await kube_client.update_service_account_image_pull_secrets(
            "default", "default", ["secret"]
        )

        service_account = await kube_client.get_service_account("default", "default")

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
