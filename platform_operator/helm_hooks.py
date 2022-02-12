import asyncio

import aiohttp

from .kube_client import KubeClient
from .models import KubeConfig

LOCK_KEY = "helm"


def start_helm_chart_upgrade_hook(
    deployment_namespace: str, deployment_name: str
) -> None:
    kube_config = KubeConfig.load_from_env()

    async def run() -> None:
        async with KubeClient(kube_config) as kube_client:
            await start_helm_chart_upgrade(
                kube_client, deployment_namespace, deployment_name
            )

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())
    loop.close()


def end_helm_chart_upgrade_hook(
    deployment_namespace: str, deployment_name: str
) -> None:
    kube_config = KubeConfig.load_from_env()

    async def run() -> None:
        async with KubeClient(kube_config) as kube_client:
            await end_helm_chart_upgrade(
                kube_client, deployment_namespace, deployment_name
            )

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())
    loop.close()


async def start_helm_chart_upgrade(
    kube_client: KubeClient, deployment_namespace: str, deployment_name: str
) -> None:
    try:
        acquire_lock = kube_client.acquire_lock(
            deployment_namespace, deployment_name, LOCK_KEY, ttl_s=15 * 60, sleep_s=5
        )
        await asyncio.wait_for(acquire_lock, 10 * 60)
    except aiohttp.ClientResponseError as ex:
        if ex.status == 404:
            pass
        else:
            raise


async def end_helm_chart_upgrade(
    kube_client: KubeClient, deployment_namespace: str, deployment_name: str
) -> None:
    try:
        await kube_client.release_lock(deployment_namespace, deployment_name, LOCK_KEY)
    except aiohttp.ClientResponseError as ex:
        if ex.status == 404:
            pass
        else:
            raise
