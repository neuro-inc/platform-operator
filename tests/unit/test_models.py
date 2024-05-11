from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import kopf
import pytest
from neuro_config_client import (
    ARecord,
    Cluster,
    DNSConfig,
    DockerRegistryConfig,
    ResourcePoolType,
)
from yarl import URL

from platform_operator.models import (
    BucketsConfig,
    BucketsProvider,
    Config,
    DockerRegistryStorageDriver,
    HelmChartNames,
    HelmChartVersions,
    HelmReleaseNames,
    IngressServiceType,
    KubeClientAuthType,
    KubeConfig,
    LabelsConfig,
    PlatformConfig,
    PlatformConfigFactory,
    RegistryConfig,
    RegistryProvider,
    StorageConfig,
    StorageType,
)


class TestConfig:
    def test_config(self) -> None:
        env = {
            "NP_NODE_NAME": "minikube",
            "NP_PLATFORM_AUTH_URL": "http://platformauthapi:8080",
            "NP_PLATFORM_INGRESS_AUTH_URL": "http://platformingressauth:8080",
            "NP_PLATFORM_CONFIG_URL": "http://platformconfig:8080",
            "NP_PLATFORM_CONFIG_WATCH_INTERVAL_S": "0.1",
            "NP_PLATFORM_ADMIN_URL": "http://platformadmin:8080",
            "NP_PLATFORM_API_URL": "http://platformapi:8080",
            "NP_PLATFORM_NOTIFICATIONS_URL": "http://platformnotifications:8080",
            "NP_CONTROLLER_LOG_LEVEL": "debug",
            "NP_CONTROLLER_RETRIES": "5",
            "NP_CONTROLLER_BACKOFF": "120",
            "NP_KUBE_VERSION": "v1.14.10",
            "NP_KUBE_URL": "https://kubernetes.default",
            "NP_KUBE_CERT_AUTHORITY_PATH": "/ca.crt",
            "NP_KUBE_CERT_AUTHORITY_DATA_PEM": "cert-authority-data",
            "NP_KUBE_AUTH_TYPE": "certificate",
            "NP_KUBE_AUTH_CERT_PATH": "/client.crt",
            "NP_KUBE_AUTH_CERT_KEY_PATH": "/client.key",
            "NP_KUBE_AUTH_TOKEN_PATH": "/token",
            "NP_KUBE_AUTH_TOKEN": "token",
            "NP_LABEL_JOB": "platform.neuromation.io/job",
            "NP_LABEL_NODE_POOL": "platform.neuromation.io/nodepool",
            "NP_LABEL_ACCELERATOR": "platform.neuromation.io/accelerator",
            "NP_LABEL_PREEMPTIBLE": "platform.neuromation.io/preemptible",
            "NP_HELM_PLATFORM_CHART_VERSION": "1.0.0",
            "NP_PLATFORM_NAMESPACE": "platform",
            "NP_PLATFORM_JOBS_NAMESPACE": "platform-jobs",
            "NP_PLATFORM_LOCK_SECRET_NAME": "platform-operator-lock",
            "NP_ACME_CA_STAGING_PATH": "/ca.pem",
            "NP_STANDALONE": "true",
        }
        assert Config.load_from_env(env) == Config(
            node_name="minikube",
            log_level="DEBUG",
            retries=5,
            backoff=120,
            kube_config=KubeConfig(
                version="1.14.10",
                url=URL("https://kubernetes.default"),
                cert_authority_path=Path("/ca.crt"),
                cert_authority_data_pem="cert-authority-data",
                auth_type=KubeClientAuthType.CERTIFICATE,
                auth_cert_path=Path("/client.crt"),
                auth_cert_key_path=Path("/client.key"),
                auth_token_path=Path("/token"),
                auth_token="token",
                conn_timeout_s=300,
                read_timeout_s=100,
                conn_pool_size=100,
            ),
            helm_release_names=HelmReleaseNames(platform="platform"),
            helm_chart_names=HelmChartNames(),
            helm_chart_versions=HelmChartVersions(platform="1.0.0"),
            platform_auth_url=URL("http://platformauthapi:8080"),
            platform_ingress_auth_url=URL("http://platformingressauth:8080"),
            platform_config_url=URL("http://platformconfig:8080"),
            platform_config_watch_interval_s=0.1,
            platform_admin_url=URL("http://platformadmin:8080"),
            platform_api_url=URL("http://platformapi:8080"),
            platform_notifications_url=URL("http://platformnotifications:8080"),
            platform_namespace="platform",
            platform_lock_secret_name="platform-operator-lock",
            acme_ca_staging_path="/ca.pem",
            is_standalone=True,
        )

    def test_config_defaults(self) -> None:
        env = {
            "NP_NODE_NAME": "minikube",
            "NP_PLATFORM_AUTH_URL": "http://platformauthapi:8080",
            "NP_PLATFORM_INGRESS_AUTH_URL": "http://platformingressauth:8080",
            "NP_PLATFORM_CONFIG_URL": "http://platformconfig:8080",
            "NP_PLATFORM_ADMIN_URL": "http://platformadmin:8080",
            "NP_PLATFORM_API_URL": "http://platformapi:8080",
            "NP_PLATFORM_NOTIFICATIONS_URL": "http://platformnotifications:8080",
            "NP_KUBE_VERSION": "v1.14.10",
            "NP_KUBE_URL": "https://kubernetes.default",
            "NP_KUBE_AUTH_TYPE": "none",
            "NP_LABEL_JOB": "platform.neuromation.io/job",
            "NP_LABEL_NODE_POOL": "platform.neuromation.io/nodepool",
            "NP_LABEL_ACCELERATOR": "platform.neuromation.io/accelerator",
            "NP_LABEL_PREEMPTIBLE": "platform.neuromation.io/preemptible",
            "NP_HELM_PLATFORM_CHART_VERSION": "1.0.0",
            "NP_PLATFORM_NAMESPACE": "platform",
            "NP_PLATFORM_LOCK_SECRET_NAME": "platform-operator-lock",
            "NP_PLATFORM_JOBS_NAMESPACE": "platform-jobs",
            "NP_ACME_CA_STAGING_PATH": "/ca.pem",
        }
        assert Config.load_from_env(env) == Config(
            node_name="minikube",
            log_level="INFO",
            retries=3,
            backoff=60,
            kube_config=KubeConfig(
                version="1.14.10",
                url=URL("https://kubernetes.default"),
                auth_type=KubeClientAuthType.NONE,
                conn_timeout_s=300,
                read_timeout_s=100,
                conn_pool_size=100,
            ),
            helm_release_names=HelmReleaseNames(platform="platform"),
            helm_chart_names=HelmChartNames(),
            helm_chart_versions=HelmChartVersions(platform="1.0.0"),
            platform_auth_url=URL("http://platformauthapi:8080"),
            platform_ingress_auth_url=URL("http://platformingressauth:8080"),
            platform_config_url=URL("http://platformconfig:8080"),
            platform_config_watch_interval_s=15,
            platform_admin_url=URL("http://platformadmin:8080"),
            platform_api_url=URL("http://platformapi:8080"),
            platform_notifications_url=URL("http://platformnotifications:8080"),
            platform_namespace="platform",
            platform_lock_secret_name="platform-operator-lock",
            acme_ca_staging_path="/ca.pem",
            is_standalone=False,
        )


class TestPlatformConfig:
    @pytest.fixture
    def traefik_service(self) -> dict[str, Any]:
        return {
            "metadata": {"name", "traefik"},
            "spec": {"type": "LoadBalancer"},
            "status": {"loadBalancer": {"ingress": [{"ip": "192.168.0.1"}]}},
        }

    @pytest.fixture
    def traefik_node_port_service(self) -> dict[str, Any]:
        return {
            "metadata": {"name", "traefik"},
            "spec": {"type": "NodePort"},
        }

    @pytest.fixture
    def aws_traefik_service(self) -> dict[str, Any]:
        return {
            "metadata": {"name", "traefik"},
            "spec": {"type": "LoadBalancer"},
            "status": {"loadBalancer": {"ingress": [{"hostname": "traefik"}]}},
        }

    @pytest.fixture
    def aws_traefik_lb(self) -> dict[str, Any]:
        return {
            "CanonicalHostedZoneId": "/hostedzone/traefik",
        }

    def test_create_dns_config_from_traefik_load_balancer_service(
        self, gcp_platform_config: PlatformConfig, traefik_service: dict[str, Any]
    ) -> None:
        result = gcp_platform_config.create_dns_config(ingress_service=traefik_service)
        dns_name = gcp_platform_config.ingress_dns_name

        assert result == DNSConfig(
            name=gcp_platform_config.ingress_dns_name,
            a_records=[
                ARecord(name=f"{dns_name}.", ips=["192.168.0.1"]),
                ARecord(name=f"*.jobs.{dns_name}.", ips=["192.168.0.1"]),
                ARecord(name=f"*.apps.{dns_name}.", ips=["192.168.0.1"]),
                ARecord(name=f"registry.{dns_name}.", ips=["192.168.0.1"]),
                ARecord(name=f"metrics.{dns_name}.", ips=["192.168.0.1"]),
            ],
        )

    def test_create_dns_config_from_traefik_node_port_service(
        self,
        gcp_platform_config: PlatformConfig,
        traefik_node_port_service: dict[str, Any],
    ) -> None:
        result = gcp_platform_config.create_dns_config(
            ingress_service=traefik_node_port_service
        )

        assert result is None

    def test_create_dns_config_from_ingress_public_ips(
        self, on_prem_platform_config: PlatformConfig
    ) -> None:
        result = on_prem_platform_config.create_dns_config()
        dns_name = on_prem_platform_config.ingress_dns_name

        assert result == DNSConfig(
            name=on_prem_platform_config.ingress_dns_name,
            a_records=[
                ARecord(name=f"{dns_name}.", ips=["192.168.0.3"]),
                ARecord(name=f"*.jobs.{dns_name}.", ips=["192.168.0.3"]),
                ARecord(name=f"*.apps.{dns_name}.", ips=["192.168.0.3"]),
                ARecord(name=f"registry.{dns_name}.", ips=["192.168.0.3"]),
                ARecord(name=f"metrics.{dns_name}.", ips=["192.168.0.3"]),
                ARecord(name=f"blob.{dns_name}.", ips=["192.168.0.3"]),
            ],
        )

    def test_create_aws_dns_config(
        self,
        aws_platform_config: PlatformConfig,
        aws_traefik_service: dict[str, Any],
        aws_traefik_lb: dict[str, Any],
    ) -> None:
        result = aws_platform_config.create_dns_config(
            ingress_service=aws_traefik_service, aws_ingress_lb=aws_traefik_lb
        )
        dns_name = aws_platform_config.ingress_dns_name

        assert result == DNSConfig(
            name=aws_platform_config.ingress_dns_name,
            a_records=[
                ARecord(
                    name=f"{dns_name}.",
                    dns_name="traefik.",
                    zone_id="/hostedzone/traefik",
                ),
                ARecord(
                    name=f"*.jobs.{dns_name}.",
                    dns_name="traefik.",
                    zone_id="/hostedzone/traefik",
                ),
                ARecord(
                    name=f"*.apps.{dns_name}.",
                    dns_name="traefik.",
                    zone_id="/hostedzone/traefik",
                ),
                ARecord(
                    name=f"registry.{dns_name}.",
                    dns_name="traefik.",
                    zone_id="/hostedzone/traefik",
                ),
                ARecord(
                    name=f"metrics.{dns_name}.",
                    dns_name="traefik.",
                    zone_id="/hostedzone/traefik",
                ),
            ],
        )

    def test_create_dns_config_none(
        self,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        result = gcp_platform_config.create_dns_config()

        assert result is None

    def test_create_orchestrator_config(
        self,
        gcp_cluster: Cluster,
        gcp_platform_config: PlatformConfig,
        resource_pool_type_factory: Callable[..., ResourcePoolType],
    ) -> None:
        result = gcp_platform_config.create_orchestrator_config(gcp_cluster)
        assert gcp_cluster.orchestrator

        assert result == replace(
            gcp_cluster.orchestrator,
            job_internal_hostname_template=f"{{job_id}}.platform-jobs",
            resource_pool_types=[
                resource_pool_type_factory("n1-highmem-8", "192.168.0.0/16")
            ],
        )

    def test_create_orchestrator_config_none(
        self,
        gcp_cluster: Cluster,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        assert gcp_cluster.orchestrator

        gcp_cluster = replace(
            gcp_cluster,
            orchestrator=replace(
                gcp_cluster.orchestrator,
                job_internal_hostname_template=f"{{job_id}}.platform-jobs",
            ),
        )
        gcp_platform_config = replace(gcp_platform_config, kubernetes_tpu_network=None)
        result = gcp_platform_config.create_orchestrator_config(gcp_cluster)

        assert result is None


class TestPlatformConfigFactory:
    @pytest.fixture
    def factory(self, config: Config) -> PlatformConfigFactory:
        return PlatformConfigFactory(config)

    def test_platform_config_with_custom_labels(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: kopf.Body,
        gcp_cluster: Cluster,
    ) -> None:
        gcp_platform_body["spec"]["kubernetes"]["nodeLabels"] = {
            "job": "job",
            "nodePool": "nodepool",
            "accelerator": "accelerator",
            "preemptible": "preemptible",
        }

        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result.node_labels == LabelsConfig(
            job="job",
            node_pool="nodepool",
            accelerator="accelerator",
            preemptible="preemptible",
        )

    def test_gcp_platform_config(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: kopf.Body,
        gcp_cluster: Cluster,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result == gcp_platform_config

    def test_gcp_platform_config_without_token(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: kopf.Body,
        gcp_cluster: Cluster,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        del gcp_platform_body["spec"]["token"]
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result == replace(gcp_platform_config, token="")

    def test_gcp_platform_config_with_empty_storage_class(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: kopf.Body,
        gcp_cluster: Cluster,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        gcp_platform_body["spec"]["kubernetes"]["standardStorageClassName"] = ""
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result == replace(gcp_platform_config, standard_storage_class_name=None)

    def test_gcp_platform_config_without_storage_class(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: kopf.Body,
        gcp_cluster: Cluster,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        del gcp_platform_body["spec"]["kubernetes"]["standardStorageClassName"]
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result == replace(gcp_platform_config, standard_storage_class_name=None)

    def test_gcp_platform_config_with_kubernetes_storage(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: kopf.Body,
        gcp_cluster: Cluster,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        gcp_platform_body["spec"]["storages"] = [
            {
                "kubernetes": {
                    "persistence": {
                        "storageClassName": "storage-class",
                        "size": "100Gi",
                    }
                }
            }
        ]
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result == replace(
            gcp_platform_config,
            storages=[
                StorageConfig(
                    type=StorageType.KUBERNETES,
                    storage_size="100Gi",
                    storage_class_name="storage-class",
                )
            ],
        )

    def test_gcp_platform_config_with_gcs_storage(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: kopf.Body,
        gcp_cluster: Cluster,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        gcp_platform_body["spec"]["storages"] = [
            {"gcs": {"bucket": "platform-storage"}}
        ]
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result == replace(
            gcp_platform_config,
            storages=[
                StorageConfig(
                    type=StorageType.GCS,
                    gcs_bucket_name="platform-storage",
                )
            ],
        )

    def test_gcp_platform_config_with_ingress_controller_disabled(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: kopf.Body,
        gcp_cluster: Cluster,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        gcp_platform_body["spec"]["ingressController"] = {"enabled": False}
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result == replace(gcp_platform_config, ingress_controller_install=False)

    def test_gcp_platform_config_with_custom_ingress_controller_replicas(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: kopf.Body,
        gcp_cluster: Cluster,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        gcp_platform_body["spec"]["ingressController"] = {"replicas": 3}
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result == replace(gcp_platform_config, ingress_controller_replicas=3)

    def test_gcp_platform_config_with_ingress_ssl_cert(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: kopf.Body,
        gcp_cluster: Cluster,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        gcp_platform_body["spec"]["ingressController"] = {
            "ssl": {
                "certificateData": "cert-data",
                "certificateKeyData": "cert-key-data",
            }
        }
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result == replace(
            gcp_platform_config,
            ingress_acme_enabled=False,
            ingress_ssl_cert_data="cert-data",
            ingress_ssl_cert_key_data="cert-key-data",
        )

    def test_gcp_platform_config_with_ingress_service_type_node_port(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: kopf.Body,
        gcp_cluster: Cluster,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        gcp_platform_body["spec"]["ingressController"] = {
            "serviceType": "NodePort",
            "nodePorts": {
                "http": 30080,
                "https": 30443,
            },
            "hostPorts": {
                "http": 80,
                "https": 443,
            },
        }
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result == replace(
            gcp_platform_config,
            ingress_service_type=IngressServiceType.NODE_PORT,
            ingress_node_port_http=30080,
            ingress_node_port_https=30443,
            ingress_host_port_http=80,
            ingress_host_port_https=443,
        )

    def test_gcp_platform_config_with_ingress_service_annotations(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: kopf.Body,
        gcp_cluster: Cluster,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        gcp_platform_body["spec"]["ingressController"] = {
            "serviceAnnotations": {"key": "value"}
        }
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result == replace(
            gcp_platform_config, ingress_service_annotations={"key": "value"}
        )

    def test_gcp_platform_config_with_ingress_load_balancer_source_ranges(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: kopf.Body,
        gcp_cluster: Cluster,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        gcp_platform_body["spec"]["ingressController"] = {
            "loadBalancerSourceRanges": ["0.0.0.0/0"]
        }
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result == replace(
            gcp_platform_config, ingress_load_balancer_source_ranges=["0.0.0.0/0"]
        )

    def test_gcp_platform_config_with_docker_config_secret_without_credentials(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: kopf.Body,
        gcp_cluster: Cluster,
    ) -> None:
        assert gcp_cluster.credentials

        gcp_cluster = replace(
            gcp_cluster,
            credentials=replace(
                gcp_cluster.credentials,
                neuro_registry=DockerRegistryConfig(
                    url=URL("https://ghcr.io/neuro-inc")
                ),
                docker_hub=None,
            ),
        )
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result.docker_config.create_secret is False
        assert not result.docker_config.secret_name
        assert result.image_pull_secret_names == []

    def test_gcp_platform_config_with_custom_docker_config_secret(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: kopf.Body,
        gcp_cluster: Cluster,
    ) -> None:
        gcp_platform_body["spec"]["kubernetes"]["dockerConfigSecret"] = {
            "create": False,
            "name": "secret",
        }
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result.docker_config.create_secret is False
        assert result.docker_config.secret_name == "secret"
        assert "secret" in result.image_pull_secret_names

    def test_on_prem_platform_config_without_disks_storage_class_name(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: kopf.Body,
        gcp_cluster: Cluster,
    ) -> None:
        del gcp_platform_body["spec"]["disks"]

        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result.disks_storage_class_name is None

    def test_gcp_platform_config_without_grafana_credentials(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: kopf.Body,
        gcp_cluster: Cluster,
    ) -> None:
        assert gcp_cluster.credentials

        gcp_cluster = replace(
            gcp_cluster,
            credentials=replace(gcp_cluster.credentials, grafana=None),
        )
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result.grafana_username is None
        assert result.grafana_password is None

    def test_gcp_platform_config_without_tracing(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: kopf.Body,
        gcp_cluster: Cluster,
    ) -> None:
        assert gcp_cluster.credentials

        gcp_cluster = replace(
            gcp_cluster,
            credentials=replace(gcp_cluster.credentials, sentry=None),
        )
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result.sentry_dsn is None
        assert result.sentry_sample_rate is None

    def test_gcp_platform_config_without_docker_hub(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: kopf.Body,
        gcp_cluster: Cluster,
    ) -> None:
        assert gcp_cluster.credentials

        gcp_cluster = replace(
            gcp_cluster,
            credentials=replace(gcp_cluster.credentials, docker_hub=None),
        )
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result.image_pull_secret_names == ["platform-docker-config"]
        assert result.docker_hub_config is None

    def test_aws_platform_config(
        self,
        factory: PlatformConfigFactory,
        aws_platform_body: kopf.Body,
        aws_cluster: Cluster,
        aws_platform_config: PlatformConfig,
    ) -> None:
        result = factory.create(aws_platform_body, aws_cluster)

        assert result == aws_platform_config

    def test_aws_platform_config_with_roles(
        self,
        factory: PlatformConfigFactory,
        aws_platform_body: kopf.Body,
        aws_cluster: Cluster,
        aws_platform_config: PlatformConfig,
    ) -> None:
        aws_platform_body["spec"]["iam"] = {
            "aws": {"roleArn": "role-arn", "s3RoleArn": "s3-role-arn"}
        }
        result = factory.create(aws_platform_body, aws_cluster)

        assert result == replace(
            aws_platform_config,
            service_account_annotations={"eks.amazonaws.com/role-arn": "role-arn"},
            aws_role_arn="role-arn",
            aws_s3_role_arn="s3-role-arn",
        )

    def test_aws_platform_config_without_registry__fails(
        self,
        factory: PlatformConfigFactory,
        aws_platform_body: kopf.Body,
        aws_cluster: Cluster,
    ) -> None:
        del aws_platform_body["spec"]["registry"]

        with pytest.raises(ValueError, match="Registry spec is empty"):
            factory.create(aws_platform_body, aws_cluster)

    def test_aws_platform_config_with_kubernetes_storage(
        self,
        factory: PlatformConfigFactory,
        aws_platform_body: kopf.Body,
        aws_cluster: Cluster,
        aws_platform_config: PlatformConfig,
    ) -> None:
        aws_platform_body["spec"]["storages"] = [
            {
                "kubernetes": {
                    "persistence": {
                        "storageClassName": "storage-class",
                        "size": "100Gi",
                    }
                }
            }
        ]
        result = factory.create(aws_platform_body, aws_cluster)

        assert result == replace(
            aws_platform_config,
            storages=[
                StorageConfig(
                    type=StorageType.KUBERNETES,
                    storage_size="100Gi",
                    storage_class_name="storage-class",
                )
            ],
        )

    def test_azure_platform_config(
        self,
        factory: PlatformConfigFactory,
        azure_platform_body: kopf.Body,
        azure_cluster: Cluster,
        azure_platform_config: PlatformConfig,
    ) -> None:
        result = factory.create(azure_platform_body, azure_cluster)

        assert result == azure_platform_config

    def test_azure_platform_config_without_registry__fails(
        self,
        factory: PlatformConfigFactory,
        azure_platform_body: kopf.Body,
        azure_cluster: Cluster,
    ) -> None:
        azure_platform_body["spec"]["registry"] = {}

        with pytest.raises(ValueError, match="Registry spec is empty"):
            factory.create(azure_platform_body, azure_cluster)

    def test_azure_platform_config_with_kubernetes_storage(
        self,
        factory: PlatformConfigFactory,
        azure_platform_body: kopf.Body,
        azure_cluster: Cluster,
        azure_platform_config: PlatformConfig,
    ) -> None:
        azure_platform_body["spec"]["storages"] = [
            {
                "kubernetes": {
                    "persistence": {
                        "storageClassName": "storage-class",
                        "size": "100Gi",
                    }
                }
            }
        ]
        result = factory.create(azure_platform_body, azure_cluster)

        assert result == replace(
            azure_platform_config,
            storages=[
                StorageConfig(
                    type=StorageType.KUBERNETES,
                    storage_size="100Gi",
                    storage_class_name="storage-class",
                )
            ],
        )

    def test_azure_platform_config_with_nfs_storage(
        self,
        factory: PlatformConfigFactory,
        azure_platform_body: kopf.Body,
        azure_cluster: Cluster,
        azure_platform_config: PlatformConfig,
    ) -> None:
        azure_platform_body["spec"]["storages"] = [
            {"nfs": {"server": "nfs-server", "path": "/path"}}
        ]
        result = factory.create(azure_platform_body, azure_cluster)

        assert result == replace(
            azure_platform_config,
            storages=[
                StorageConfig(
                    type=StorageType.NFS,
                    nfs_server="nfs-server",
                    nfs_export_path="/path",
                )
            ],
        )

    def test_azure_platform_config_without_blob_storage__fails(
        self,
        factory: PlatformConfigFactory,
        azure_platform_body: kopf.Body,
        azure_cluster: Cluster,
    ) -> None:
        azure_platform_body["spec"]["blobStorage"] = {}

        with pytest.raises(ValueError, match="Blob storage spec is empty"):
            factory.create(azure_platform_body, azure_cluster)

    def test_on_prem_platform_config(
        self,
        factory: PlatformConfigFactory,
        on_prem_platform_body: kopf.Body,
        on_prem_cluster: Cluster,
        on_prem_platform_config: PlatformConfig,
    ) -> None:
        result = factory.create(on_prem_platform_body, on_prem_cluster)

        assert result == on_prem_platform_config

    def test_on_prem_platform_config_with_nfs_storage(
        self,
        factory: PlatformConfigFactory,
        on_prem_platform_body: kopf.Body,
        on_prem_cluster: Cluster,
        on_prem_platform_config: PlatformConfig,
    ) -> None:
        on_prem_platform_body["spec"]["storages"] = [
            {"nfs": {"server": "nfs-server", "path": "/path"}}
        ]
        result = factory.create(on_prem_platform_body, on_prem_cluster)

        assert result == replace(
            on_prem_platform_config,
            storages=[
                StorageConfig(
                    type=StorageType.NFS,
                    nfs_server="nfs-server",
                    nfs_export_path="/path",
                )
            ],
        )

    def test_on_prem_platform_config_with_smb_storage(
        self,
        factory: PlatformConfigFactory,
        on_prem_platform_body: kopf.Body,
        on_prem_cluster: Cluster,
        on_prem_platform_config: PlatformConfig,
    ) -> None:
        on_prem_platform_body["spec"]["storages"] = [
            {
                "smb": {
                    "server": "smb-server",
                    "shareName": "smb-share",
                    "username": "smb-username",
                    "password": "smb-password",
                }
            }
        ]
        result = factory.create(on_prem_platform_body, on_prem_cluster)

        assert result == replace(
            on_prem_platform_config,
            storages=[
                StorageConfig(
                    type=StorageType.SMB,
                    smb_server="smb-server",
                    smb_share_name="smb-share",
                    smb_username="smb-username",
                    smb_password="smb-password",
                )
            ],
        )

    def test_on_prem_platform_config_without_metrics(
        self,
        config: Config,
        on_prem_platform_body: kopf.Body,
        on_prem_cluster: Cluster,
    ) -> None:
        config = replace(config, is_standalone=True)
        del on_prem_platform_body["spec"]["monitoring"]["metrics"]
        factory = PlatformConfigFactory(config)

        result = factory.create(on_prem_platform_body, on_prem_cluster)

        assert result.monitoring.metrics_enabled is False

    def test_on_prem_platform_config_with_metrics_retention_time(
        self,
        factory: PlatformConfigFactory,
        on_prem_platform_body: kopf.Body,
        on_prem_cluster: Cluster,
    ) -> None:
        on_prem_platform_body["spec"]["monitoring"]["metrics"]["retentionTime"] = "1d"

        result = factory.create(on_prem_platform_body, on_prem_cluster)

        assert result.monitoring.metrics_retention_time == "1d"

    def test_on_prem_platform_config_with_docker_registry_filesystem(
        self,
        factory: PlatformConfigFactory,
        on_prem_platform_body: kopf.Body,
        on_prem_cluster: Cluster,
    ) -> None:
        on_prem_platform_body["spec"]["registry"] = {
            "docker": {
                "url": "http://docker-registry",
                "username": "docker_username",
                "password": "docker_password",
            }
        }

        result = factory.create(on_prem_platform_body, on_prem_cluster)

        assert result.registry == RegistryConfig(
            provider=RegistryProvider.DOCKER,
            docker_registry_install=False,
            docker_registry_url=URL("http://docker-registry"),
            docker_registry_username="docker_username",
            docker_registry_password="docker_password",
        )

    def test_on_prem_platform_config_with_unprotected_docker_registry(
        self,
        factory: PlatformConfigFactory,
        on_prem_platform_body: kopf.Body,
        on_prem_cluster: Cluster,
    ) -> None:
        on_prem_platform_body["spec"]["registry"] = {
            "docker": {"url": "http://docker-registry"}
        }

        result = factory.create(on_prem_platform_body, on_prem_cluster)

        assert result.registry == RegistryConfig(
            provider=RegistryProvider.DOCKER,
            docker_registry_install=False,
            docker_registry_url=URL("http://docker-registry"),
            docker_registry_username="",
            docker_registry_password="",
        )

    def test_on_prem_platform_config_with_docker_registry__s3_minio(
        self,
        factory: PlatformConfigFactory,
        on_prem_platform_body: kopf.Body,
        on_prem_cluster: Cluster,
    ) -> None:
        on_prem_platform_body["spec"]["registry"] = {
            "blobStorage": {
                "bucket": "job-images",
            }
        }

        result = factory.create(on_prem_platform_body, on_prem_cluster)

        assert result.registry == RegistryConfig(
            provider=RegistryProvider.DOCKER,
            docker_registry_install=True,
            docker_registry_url=URL("http://platform-docker-registry:5000"),
            docker_registry_storage_driver=DockerRegistryStorageDriver.S3,
            docker_registry_s3_endpoint=URL("http://platform-minio:9000"),
            docker_registry_s3_bucket="job-images",
            docker_registry_s3_region="minio",
            docker_registry_s3_access_key="username",
            docker_registry_s3_secret_key="password",
            docker_registry_s3_disable_redirect=True,
            docker_registry_s3_force_path_style=True,
        )

    def test_on_prem_platform_config_with_minio_buckets(
        self,
        factory: PlatformConfigFactory,
        on_prem_platform_body: kopf.Body,
        on_prem_cluster: Cluster,
        cluster_name: str,
    ) -> None:
        on_prem_platform_body["spec"]["blobStorage"] = {
            "minio": {
                "url": "http://minio",
                "region": "minio_region",
                "accessKey": "minio_access_key",
                "secretKey": "minio_secret_key",
            }
        }

        result = factory.create(on_prem_platform_body, on_prem_cluster)

        assert result.buckets == BucketsConfig(
            provider=BucketsProvider.MINIO,
            minio_install=False,
            minio_url=URL("http://minio"),
            minio_public_url=URL(f"https://blob.{cluster_name}.org.neu.ro"),
            minio_region="minio_region",
            minio_access_key="minio_access_key",
            minio_secret_key="minio_secret_key",
        )

    def test_on_prem_platform_config_with_emc_ecs_buckets(
        self,
        factory: PlatformConfigFactory,
        on_prem_platform_body: kopf.Body,
        on_prem_cluster: Cluster,
    ) -> None:
        on_prem_platform_body["spec"]["blobStorage"] = {
            "emcEcs": {
                "accessKeyId": "key_id",
                "secretAccessKey": "secret_key",
                "s3Endpoint": "https://emc-ecs.s3",
                "managementEndpoint": "https://emc-ecs.management",
                "s3Role": "s3-role",
            }
        }

        result = factory.create(on_prem_platform_body, on_prem_cluster)

        assert result.buckets == BucketsConfig(
            provider=BucketsProvider.EMC_ECS,
            emc_ecs_access_key_id="key_id",
            emc_ecs_secret_access_key="secret_key",
            emc_ecs_s3_endpoint=URL("https://emc-ecs.s3"),
            emc_ecs_management_endpoint=URL("https://emc-ecs.management"),
            emc_ecs_s3_assumable_role="s3-role",
        )

    def test_on_prem_platform_config_with_open_stack_buckets(
        self,
        factory: PlatformConfigFactory,
        on_prem_platform_body: kopf.Body,
        on_prem_cluster: Cluster,
    ) -> None:
        on_prem_platform_body["spec"]["blobStorage"] = {
            "openStack": {
                "username": "account_id",
                "password": "password",
                "region": "region",
                "s3Endpoint": "https://os.s3",
                "endpoint": "https://os.management",
            }
        }

        result = factory.create(on_prem_platform_body, on_prem_cluster)

        assert result.buckets == BucketsConfig(
            provider=BucketsProvider.OPEN_STACK,
            open_stack_username="account_id",
            open_stack_password="password",
            open_stack_s3_endpoint=URL("https://os.s3"),
            open_stack_endpoint=URL("https://os.management"),
            open_stack_region_name="region",
        )

    def test_vcd_platform_config(
        self,
        factory: PlatformConfigFactory,
        vcd_platform_body: kopf.Body,
        vcd_cluster: Cluster,
        vcd_platform_config: PlatformConfig,
    ) -> None:
        result = factory.create(vcd_platform_body, vcd_cluster)

        assert result == vcd_platform_config
