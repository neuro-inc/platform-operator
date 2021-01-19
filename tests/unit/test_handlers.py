import logging
from dataclasses import replace
from typing import Any, Dict, Iterator
from unittest import mock

import kopf
import pytest
from kopf.structs import bodies

from platform_operator.aws_client import AwsElbClient
from platform_operator.certificate_store import CertificateStore
from platform_operator.config_client import ConfigClient
from platform_operator.helm_client import HelmClient
from platform_operator.kube_client import (
    KubeClient,
    PlatformConditionType,
    PlatformStatusManager,
)
from platform_operator.models import (
    Cluster,
    Config,
    PlatformConfig,
    PlatformConfigFactory,
)


@pytest.fixture
def setup_app(
    config: Config,
    kube_client: KubeClient,
    config_client: ConfigClient,
    helm_client: HelmClient,
    certificate_store: CertificateStore,
) -> Iterator[None]:
    with mock.patch.object(Config, "load_from_env") as method:
        method.return_value = config

        from platform_operator.handlers import App

        with mock.patch("platform_operator.handlers.app", spec=App) as app:
            app.kube_client = kube_client
            app.config_client = config_client
            app.helm_client = helm_client
            app.certificate_store = certificate_store
            app.platform_config_factory = PlatformConfigFactory(config)
            yield


@pytest.fixture
def kube_client() -> mock.AsyncMock:
    return mock.AsyncMock(KubeClient)


@pytest.fixture
def config_client() -> mock.Mock:
    return mock.AsyncMock(ConfigClient)


@pytest.fixture
def helm_client() -> mock.Mock:
    return mock.AsyncMock(HelmClient)


@pytest.fixture
def logger() -> logging.Logger:
    return logging.getLogger("controller")


@pytest.fixture
def certificate_store() -> mock.Mock:
    return mock.AsyncMock(CertificateStore)


@pytest.fixture
def configure_cluster() -> Iterator[mock.Mock]:
    with mock.patch(
        "platform_operator.handlers.configure_cluster"
    ) as configure_cluster:
        yield configure_cluster


@pytest.fixture
def status_manager() -> Iterator[mock.Mock]:
    with mock.patch(
        "platform_operator.handlers.PlatformStatusManager", spec=PlatformStatusManager
    ) as manager_class:
        yield manager_class.return_value


@pytest.fixture
def aws_elb_client() -> Iterator[mock.Mock]:
    with mock.patch(
        "platform_operator.handlers.AwsElbClient", spec=AwsElbClient
    ) as client_class:
        client_instance = mock.AsyncMock(AwsElbClient)
        client_instance.__aenter__.return_value = client_instance
        client_class.return_value = client_instance
        yield client_instance


@pytest.fixture
def traefik_service() -> Dict[str, Any]:
    return {
        "status": {"loadBalancer": {"ingress": [{"ip": "192.168.0.1"}]}},
    }


@pytest.fixture
def aws_traefik_service() -> Dict[str, Any]:
    return {
        "status": {"loadBalancer": {"ingress": [{"hostname": "platform-traefik"}]}},
    }


@pytest.fixture
def aws_traefik_lb() -> Dict[str, Any]:
    return {
        "CanonicalHostedZoneNameID": "/hostedzone/traefik",
    }


@pytest.fixture
def service_account() -> Dict[str, Any]:
    return {"secrets": [{"name": "token"}]}


@pytest.fixture
def service_account_secret() -> Dict[str, Any]:
    return {"data": {"ca.crt": "cert-authority-data", "token": "token"}}


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_app")
async def test_configure_aws_cluster(
    kube_client: mock.Mock,
    config_client: mock.Mock,
    aws_elb_client: mock.Mock,
    aws_platform_config: PlatformConfig,
    aws_traefik_service: Dict[str, Any],
    aws_traefik_lb: Dict[str, Any],
    service_account: Dict[str, Any],
    service_account_secret: Dict[str, Any],
) -> None:
    from platform_operator.handlers import configure_cluster as _configure_cluster

    kube_client.get_service_account.return_value = service_account
    kube_client.get_secret.return_value = service_account_secret
    kube_client.get_service.side_effect = [aws_traefik_service]
    aws_elb_client.get_load_balancer_by_dns_name.side_effect = [aws_traefik_lb]

    await _configure_cluster(aws_platform_config)

    kube_client.get_service.assert_has_awaits(
        [mock.call(namespace="platform", name="platform-traefik")]
    )
    aws_elb_client.get_load_balancer_by_dns_name.assert_has_awaits(
        [mock.call("platform-traefik")]
    )
    config_client.patch_cluster.assert_awaited_with(
        cluster_name=aws_platform_config.cluster_name,
        token=aws_platform_config.token,
        payload=aws_platform_config.create_cluster_config(
            service_account_secret=service_account_secret,
            traefik_service=aws_traefik_service,
            aws_traefik_lb=aws_traefik_lb,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_app")
async def test_configure_cluster(
    gcp_platform_config: PlatformConfig,
    kube_client: mock.Mock,
    config_client: mock.Mock,
    service_account: Dict[str, Any],
    service_account_secret: Dict[str, Any],
    traefik_service: Dict[str, Any],
) -> None:
    from platform_operator.handlers import configure_cluster as _configure_cluster

    kube_client.get_service.side_effect = [traefik_service]
    kube_client.get_service_account.return_value = service_account
    kube_client.get_secret.return_value = service_account_secret

    await _configure_cluster(gcp_platform_config)

    kube_client.get_service.assert_has_awaits(
        [mock.call(namespace="platform", name="platform-traefik")]
    )
    kube_client.get_service_account.assert_awaited_with(
        namespace="platform-jobs",
        name="platform-jobs",
    )
    kube_client.get_secret.assert_awaited_with(namespace="platform-jobs", name="token")
    config_client.patch_cluster.assert_awaited_with(
        cluster_name=gcp_platform_config.cluster_name,
        token=gcp_platform_config.token,
        payload=gcp_platform_config.create_cluster_config(
            service_account_secret=service_account_secret,
            traefik_service=traefik_service,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_app")
async def test_configure_cluster_with_ingress_controller_disabled(
    gcp_platform_config: PlatformConfig,
    kube_client: mock.Mock,
    config_client: mock.Mock,
    service_account: Dict[str, Any],
    service_account_secret: Dict[str, Any],
) -> None:
    from platform_operator.handlers import configure_cluster as _configure_cluster

    gcp_platform_config = replace(gcp_platform_config, ingress_controller_enabled=False)

    kube_client.get_service_account.return_value = service_account
    kube_client.get_secret.return_value = service_account_secret

    await _configure_cluster(gcp_platform_config)

    kube_client.get_service_account.assert_awaited_with(
        namespace="platform-jobs",
        name="platform-jobs",
    )
    kube_client.get_secret.assert_awaited_with(namespace="platform-jobs", name="token")
    config_client.patch_cluster.assert_awaited_with(
        cluster_name=gcp_platform_config.cluster_name,
        token=gcp_platform_config.token,
        payload=gcp_platform_config.create_cluster_config(
            service_account_secret=service_account_secret,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_app")
async def test_deploy(
    status_manager: mock.AsyncMock,
    config_client: mock.AsyncMock,
    kube_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    certificate_store: mock.AsyncMock,
    configure_cluster: mock.AsyncMock,
    logger: logging.Logger,
    config: Config,
    gcp_cluster: Cluster,
    gcp_platform_body: bodies.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import deploy

    status_manager.is_condition_satisfied.return_value = False
    config_client.get_cluster.return_value = gcp_cluster

    await deploy(
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    config_client.get_cluster.assert_awaited_once_with(
        cluster_name=gcp_platform_config.cluster_name,
        token=gcp_platform_body["spec"]["token"],
    )

    kube_client.update_service_account_image_pull_secrets.assert_awaited_once_with(
        namespace=gcp_platform_config.namespace,
        name=gcp_platform_config.service_account_name,
        image_pull_secrets=gcp_platform_config.image_pull_secret_names,
    )

    helm_client.init.assert_awaited_once_with(client_only=True, skip_refresh=True)
    helm_client.add_repo.assert_has_awaits(
        [mock.call(config.helm_stable_repo), mock.call(gcp_platform_config.helm_repo)]
    )
    helm_client.update_repo.assert_awaited_once()
    helm_client.upgrade.assert_awaited_once_with(
        "platform",
        "neuro/platform",
        values=mock.ANY,
        version="1.0.0",
        namespace="platform",
        install=True,
        wait=True,
        timeout=600,
    )

    certificate_store.wait_till_certificate_created.assert_awaited_once()
    configure_cluster.assert_awaited_once_with(gcp_platform_config)

    status_manager.start_deployment.assert_awaited_once_with(0)
    status_manager.transition.assert_any_call(PlatformConditionType.PLATFORM_DEPLOYED)
    status_manager.transition.assert_any_call(PlatformConditionType.CERTIFICATE_CREATED)
    status_manager.transition.assert_any_call(PlatformConditionType.CLUSTER_CONFIGURED)
    status_manager.complete_deployment.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_app")
async def test_deploy_with_ingress_controller_disabled(
    status_manager: mock.AsyncMock,
    config_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    certificate_store: mock.AsyncMock,
    configure_cluster: mock.AsyncMock,
    logger: logging.Logger,
    config: Config,
    gcp_cluster: Cluster,
    gcp_platform_body: bodies.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import deploy

    gcp_platform_body["spec"]["kubernetes"]["ingressController"] = {"enabled": False}
    gcp_platform_config = replace(gcp_platform_config, ingress_controller_enabled=False)

    status_manager.is_condition_satisfied.return_value = False
    config_client.get_cluster.return_value = gcp_cluster

    await deploy(
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    config_client.get_cluster.assert_awaited_once_with(
        cluster_name=gcp_platform_config.cluster_name,
        token=gcp_platform_body["spec"]["token"],
    )

    helm_client.init.assert_awaited_once_with(client_only=True, skip_refresh=True)
    helm_client.add_repo.assert_has_awaits(
        [mock.call(config.helm_stable_repo), mock.call(gcp_platform_config.helm_repo)]
    )
    helm_client.update_repo.assert_awaited_once()
    helm_client.upgrade.assert_awaited_once_with(
        "platform",
        "neuro/platform",
        values=mock.ANY,
        version="1.0.0",
        namespace="platform",
        install=True,
        wait=True,
        timeout=600,
    )

    certificate_store.wait_till_certificate_created.assert_not_awaited()
    configure_cluster.assert_awaited_once_with(gcp_platform_config)

    status_manager.start_deployment.assert_awaited_once_with(0)
    status_manager.transition.assert_any_call(PlatformConditionType.PLATFORM_DEPLOYED)
    status_manager.transition.assert_any_call(PlatformConditionType.CLUSTER_CONFIGURED)
    status_manager.complete_deployment.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_app")
async def test_deploy_gcp_with_gcs_storage(
    status_manager: mock.AsyncMock,
    config_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    logger: logging.Logger,
    gcp_cluster: Cluster,
    gcp_platform_body: bodies.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import deploy

    status_manager.is_condition_satisfied.return_value = False
    config_client.get_cluster.return_value = gcp_cluster
    gcp_platform_body["spec"]["storage"] = {"gcs": {"bucket": "storage"}}

    await deploy(
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    helm_client.upgrade.assert_any_await(
        "platform-obs-csi-driver",
        "neuro/obs-csi-driver",
        values=mock.ANY,
        version="2.0.0",
        namespace="platform",
        install=True,
        wait=True,
        timeout=600,
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_app")
async def test_deploy_on_prem(
    status_manager: mock.AsyncMock,
    config_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    logger: logging.Logger,
    on_prem_cluster: Cluster,
    on_prem_platform_body: bodies.Body,
    on_prem_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import deploy

    status_manager.is_condition_satisfied.return_value = False
    config_client.get_cluster.return_value = on_prem_cluster

    await deploy(
        name=on_prem_platform_config.cluster_name,
        body=on_prem_platform_body,
        logger=logger,
        retry=0,
    )

    helm_client.upgrade.assert_any_await(
        "platform-nfs-server",
        "neuro/nfs-server",
        values=mock.ANY,
        version="3.0.0",
        namespace="platform",
        install=True,
        wait=True,
        timeout=600,
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_app")
async def test_deploy_with_all_components_deployed(
    status_manager: mock.AsyncMock,
    config_client: mock.AsyncMock,
    kube_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    certificate_store: mock.AsyncMock,
    configure_cluster: mock.AsyncMock,
    logger: logging.Logger,
    config: Config,
    gcp_cluster: Cluster,
    gcp_platform_body: bodies.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import deploy

    status_manager.is_condition_satisfied.return_value = True
    config_client.get_cluster.return_value = gcp_cluster

    await deploy(
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    config_client.get_cluster.assert_awaited_once_with(
        cluster_name=gcp_platform_config.cluster_name,
        token=gcp_platform_body["spec"]["token"],
    )

    kube_client.update_service_account_image_pull_secrets.assert_not_awaited()

    helm_client.init.assert_awaited_once_with(client_only=True, skip_refresh=True)
    helm_client.add_repo.assert_has_awaits(
        [mock.call(config.helm_stable_repo), mock.call(gcp_platform_config.helm_repo)]
    )
    helm_client.update_repo.assert_awaited_once()
    helm_client.upgrade.assert_not_awaited()

    certificate_store.wait_till_certificate_created.assert_not_awaited()
    configure_cluster.assert_not_awaited()

    status_manager.start_deployment.assert_awaited_once_with(0)
    status_manager.complete_deployment.assert_awaited_once()
    status_manager.transition.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_app")
async def test_deploy_with_retries_exceeded(
    status_manager: mock.AsyncMock,
    logger: logging.Logger,
    config: Config,
    gcp_platform_body: bodies.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import deploy

    with pytest.raises(kopf.HandlerRetriesError):
        await deploy(
            name=gcp_platform_config.cluster_name,
            body=gcp_platform_body,
            logger=logger,
            retry=config.retries + 1,
        )

    status_manager.fail_deployment.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_app")
async def test_deploy_with_invalid_spec(
    status_manager: mock.AsyncMock,
    logger: logging.Logger,
    config: Config,
    gcp_platform_body: bodies.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import deploy

    del gcp_platform_body["spec"]["storage"]

    with pytest.raises(kopf.PermanentError, match="Invalid platform configuration"):
        await deploy(
            name=gcp_platform_config.cluster_name,
            body=gcp_platform_body,
            logger=logger,
            retry=0,
        )

    status_manager.fail_deployment.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_app")
async def test_delete(
    status_manager: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    config_client: mock.AsyncMock,
    kube_client: mock.AsyncMock,
    logger: logging.Logger,
    gcp_cluster: Cluster,
    gcp_platform_body: bodies.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import delete

    config_client.get_cluster.return_value = gcp_cluster

    await delete(
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    helm_client.init.assert_awaited_once_with(client_only=True, skip_refresh=True)
    helm_client.delete.assert_awaited_once_with("platform", purge=True)

    kube_client.wait_till_pods_deleted.assert_has_awaits(
        [
            mock.call(namespace="platform-jobs"),
            mock.call(
                namespace="platform", label_selector={"service": "platformstorageapi"}
            ),
        ]
    )

    status_manager.start_deletion.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_app")
async def test_delete_gcp_with_gcs_storage(
    status_manager: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    config_client: mock.AsyncMock,
    logger: logging.Logger,
    gcp_cluster: Cluster,
    gcp_platform_body: bodies.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import delete

    config_client.get_cluster.return_value = gcp_cluster
    gcp_platform_body["spec"]["storage"] = {"gcs": {"bucket": "storage"}}

    await delete(
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    helm_client.delete.assert_has_awaits(
        [
            mock.call("platform", purge=True),
            mock.call("platform-obs-csi-driver", purge=True),
        ]
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_app")
async def test_delete_on_prem(
    status_manager: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    config_client: mock.AsyncMock,
    logger: logging.Logger,
    on_prem_cluster: Cluster,
    on_prem_platform_body: bodies.Body,
    on_prem_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import delete

    config_client.get_cluster.return_value = on_prem_cluster

    await delete(
        name=on_prem_platform_config.cluster_name,
        body=on_prem_platform_body,
        logger=logger,
        retry=0,
    )

    helm_client.delete.assert_has_awaits(
        [
            mock.call("platform", purge=True),
            mock.call("platform-nfs-server", purge=True),
        ]
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_app")
async def test_delete_with_invalid_configuration(
    status_manager: mock.AsyncMock,
    logger: logging.Logger,
    helm_client: mock.AsyncMock,
    gcp_platform_body: bodies.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import delete

    del gcp_platform_body["spec"]["storage"]

    await delete(
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    status_manager.start_deletion.assert_awaited_once()
    helm_client.init.assert_not_awaited()
