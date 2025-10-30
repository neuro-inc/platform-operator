from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import kopf
import pytest
from neuro_config_client import (
    Cluster,
    DockerRegistryConfig,
)
from yarl import URL

from platform_operator.models import (
    BucketsConfig,
    BucketsProvider,
    Config,
    DockerRegistryStorageDriver,
    HelmChartVersions,
    HelmReleaseNames,
    IngressServiceType,
    KubeClientAuthType,
    KubeConfig,
    LabelsConfig,
    PlatformConfig,
    PlatformConfigFactory,
    PlatformStorageSpec,
    RegistryConfig,
    RegistryProvider,
)


class TestConfig:
    def test_config(self) -> None:
        env = {
            "NP_PLATFORM_AUTH_URL": "http://platformauthapi:8080",
            "NP_PLATFORM_INGRESS_AUTH_URL": "http://platformingressauth:8080",
            "NP_PLATFORM_CONFIG_URL": "http://platformconfig:8080",
            "NP_PLATFORM_CONFIG_WATCH_INTERVAL_S": "0.1",
            "NP_PLATFORM_ADMIN_URL": "http://platformadmin:8080",
            "NP_PLATFORM_API_URL": "http://platformapi:8080",
            "NP_PLATFORM_APPS_URL": "http://platformapps:8080",
            "NP_PLATFORM_NOTIFICATIONS_URL": "http://platformnotifications:8080",
            "NP_PLATFORM_EVENTS_URL": "http://platform-events:8080",
            "NP_CONTROLLER_LOG_LEVEL": "debug",
            "NP_CONTROLLER_RETRIES": "5",
            "NP_CONTROLLER_BACKOFF": "120",
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
            log_level="DEBUG",
            retries=5,
            backoff=120,
            kube_config=KubeConfig(
                url=URL("https://kubernetes.default"),
                auth_type=KubeClientAuthType.CERTIFICATE,
                cert_authority_path=Path("/ca.crt"),
                auth_cert_path=Path("/client.crt"),
                auth_cert_key_path=Path("/client.key"),
                auth_token_path=Path("/token"),
                conn_timeout_s=300,
                read_timeout_s=100,
                conn_pool_size=100,
            ),
            helm_release_names=HelmReleaseNames(platform="platform"),
            helm_chart_versions=HelmChartVersions(platform="1.0.0"),
            platform_auth_url=URL("http://platformauthapi:8080"),
            platform_ingress_auth_url=URL("http://platformingressauth:8080"),
            platform_config_url=URL("http://platformconfig:8080"),
            platform_config_watch_interval_s=0.1,
            platform_admin_url=URL("http://platformadmin:8080"),
            platform_api_url=URL("http://platformapi:8080"),
            platform_apps_url=URL("http://platformapps:8080"),
            platform_notifications_url=URL("http://platformnotifications:8080"),
            platform_events_url=URL("http://platform-events:8080"),
            platform_namespace="platform",
            platform_lock_secret_name="platform-operator-lock",
            acme_ca_staging_path="/ca.pem",
            is_standalone=True,
        )

    def test_config_defaults(self) -> None:
        env = {
            "NP_PLATFORM_AUTH_URL": "http://platformauthapi:8080",
            "NP_PLATFORM_INGRESS_AUTH_URL": "http://platformingressauth:8080",
            "NP_PLATFORM_CONFIG_URL": "http://platformconfig:8080",
            "NP_PLATFORM_ADMIN_URL": "http://platformadmin:8080",
            "NP_PLATFORM_API_URL": "http://platformapi:8080",
            "NP_PLATFORM_APPS_URL": "http://platformapps:8080",
            "NP_PLATFORM_NOTIFICATIONS_URL": "http://platformnotifications:8080",
            "NP_PLATFORM_EVENTS_URL": "http://platform-events:8080",
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
            log_level="INFO",
            retries=3,
            backoff=60,
            kube_config=KubeConfig(
                url=URL("https://kubernetes.default"),
                auth_type=KubeClientAuthType.NONE,
                conn_timeout_s=300,
                read_timeout_s=100,
                conn_pool_size=100,
            ),
            helm_release_names=HelmReleaseNames(platform="platform"),
            helm_chart_versions=HelmChartVersions(platform="1.0.0"),
            platform_auth_url=URL("http://platformauthapi:8080"),
            platform_ingress_auth_url=URL("http://platformingressauth:8080"),
            platform_config_url=URL("http://platformconfig:8080"),
            platform_config_watch_interval_s=15,
            platform_admin_url=URL("http://platformadmin:8080"),
            platform_api_url=URL("http://platformapi:8080"),
            platform_apps_url=URL("http://platformapps:8080"),
            platform_notifications_url=URL("http://platformnotifications:8080"),
            platform_events_url=URL("http://platform-events:8080"),
            platform_namespace="platform",
            platform_lock_secret_name="platform-operator-lock",
            acme_ca_staging_path="/ca.pem",
            is_standalone=False,
        )


class TestPlatformConfigFactory:
    @pytest.fixture
    def factory(self, config: Config) -> PlatformConfigFactory:
        return PlatformConfigFactory(config)

    def test_platform_config_with_custom_labels(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        gcp_platform_body: kopf.Body,
    ) -> None:
        gcp_platform_body["spec"]["kubernetes"]["nodeLabels"] = {
            "job": "job",
            "nodePool": "nodepool",
            "accelerator": "accelerator",
            "preemptible": "preemptible",
        }

        result = factory.create(gcp_platform_body, cluster)

        assert result.node_labels == LabelsConfig(
            job="job",
            node_pool="nodepool",
            accelerator="accelerator",
            preemptible="preemptible",
        )

    def test_gcp_platform_config(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        gcp_platform_body: kopf.Body,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        result = factory.create(gcp_platform_body, cluster)

        assert result == gcp_platform_config

    def test_gcp_platform_config_without_token(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        gcp_platform_body: kopf.Body,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        del gcp_platform_body["spec"]["token"]
        result = factory.create(gcp_platform_body, cluster)

        assert result == replace(gcp_platform_config, token="")

    def test_gcp_platform_config_with_empty_storage_class(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        gcp_platform_body: kopf.Body,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        gcp_platform_body["spec"]["kubernetes"]["standardStorageClassName"] = ""
        result = factory.create(gcp_platform_body, cluster)

        assert result == replace(gcp_platform_config, standard_storage_class_name=None)

    def test_gcp_platform_config_without_storage_class(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        gcp_platform_body: kopf.Body,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        del gcp_platform_body["spec"]["kubernetes"]["standardStorageClassName"]
        result = factory.create(gcp_platform_body, cluster)

        assert result == replace(gcp_platform_config, standard_storage_class_name=None)

    def test_gcp_platform_config_with_ingress_controller_disabled(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        gcp_platform_body: kopf.Body,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        gcp_platform_body["spec"]["ingressController"] = {"enabled": False}
        result = factory.create(gcp_platform_body, cluster)

        assert result == replace(gcp_platform_config, ingress_controller_install=False)

    def test_gcp_platform_config_with_custom_ingress_controller_replicas(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        gcp_platform_body: kopf.Body,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        gcp_platform_body["spec"]["ingressController"] = {"replicas": 3}
        result = factory.create(gcp_platform_body, cluster)

        assert result == replace(gcp_platform_config, ingress_controller_replicas=3)

    def test_gcp_platform_config_with_ingress_ssl_cert(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        gcp_platform_body: kopf.Body,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        gcp_platform_body["spec"]["ingressController"] = {
            "ssl": {
                "certificateData": "cert-data",
                "certificateKeyData": "cert-key-data",
            }
        }
        result = factory.create(gcp_platform_body, cluster)

        assert result == replace(
            gcp_platform_config,
            ingress_acme_enabled=False,
            ingress_ssl_cert_data="cert-data",
            ingress_ssl_cert_key_data="cert-key-data",
        )

    def test_gcp_platform_config_with_ingress_service_type_node_port(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        gcp_platform_body: kopf.Body,
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
        result = factory.create(gcp_platform_body, cluster)

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
        cluster: Cluster,
        gcp_platform_body: kopf.Body,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        gcp_platform_body["spec"]["ingressController"] = {
            "serviceAnnotations": {"key": "value"}
        }
        result = factory.create(gcp_platform_body, cluster)

        assert result == replace(
            gcp_platform_config, ingress_service_annotations={"key": "value"}
        )

    def test_gcp_platform_config_with_ingress_load_balancer_source_ranges(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        gcp_platform_body: kopf.Body,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        gcp_platform_body["spec"]["ingressController"] = {
            "loadBalancerSourceRanges": ["0.0.0.0/0"]
        }
        result = factory.create(gcp_platform_body, cluster)

        assert result == replace(
            gcp_platform_config, ingress_load_balancer_source_ranges=["0.0.0.0/0"]
        )

    def test_gcp_platform_config_with_docker_config_secret_without_credentials(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        gcp_platform_body: kopf.Body,
    ) -> None:
        assert cluster.credentials

        cluster = replace(
            cluster,
            credentials=replace(
                cluster.credentials,
                neuro_registry=DockerRegistryConfig(
                    url=URL("https://ghcr.io/neuro-inc")
                ),
                docker_hub=None,
            ),
        )
        result = factory.create(gcp_platform_body, cluster)

        assert result.docker_config.create_secret is False
        assert not result.docker_config.secret_name
        assert result.image_pull_secret_names == []

    def test_gcp_platform_config_with_custom_docker_config_secret(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        gcp_platform_body: kopf.Body,
    ) -> None:
        gcp_platform_body["spec"]["kubernetes"]["dockerConfigSecret"] = {
            "create": False,
            "name": "secret",
        }
        result = factory.create(gcp_platform_body, cluster)

        assert result.docker_config.create_secret is False
        assert result.docker_config.secret_name == "secret"
        assert "secret" in result.image_pull_secret_names

    def test_on_prem_platform_config_without_disks_storage_class_name(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        gcp_platform_body: kopf.Body,
    ) -> None:
        del gcp_platform_body["spec"]["disks"]

        result = factory.create(gcp_platform_body, cluster)

        assert result.disks_storage_class_name is None

    def test_gcp_platform_config_without_grafana_credentials(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        gcp_platform_body: kopf.Body,
    ) -> None:
        assert cluster.credentials

        cluster = replace(
            cluster,
            credentials=replace(cluster.credentials, grafana=None),
        )
        result = factory.create(gcp_platform_body, cluster)

        assert result.grafana_username is None
        assert result.grafana_password is None

    def test_gcp_platform_config_without_tracing(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        gcp_platform_body: kopf.Body,
    ) -> None:
        assert cluster.credentials

        cluster = replace(
            cluster,
            credentials=replace(cluster.credentials, sentry=None),
        )
        result = factory.create(gcp_platform_body, cluster)

        assert result.sentry_dsn is None
        assert result.sentry_sample_rate is None

    def test_gcp_platform_config_without_docker_hub(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        gcp_platform_body: kopf.Body,
    ) -> None:
        assert cluster.credentials

        cluster = replace(
            cluster,
            credentials=replace(cluster.credentials, docker_hub=None),
        )
        result = factory.create(gcp_platform_body, cluster)

        assert result.image_pull_secret_names == ["platform-docker-config"]
        assert result.docker_hub_config is None

    def test_aws_platform_config(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        aws_platform_body: kopf.Body,
        aws_platform_config: PlatformConfig,
    ) -> None:
        result = factory.create(aws_platform_body, cluster)

        assert result == aws_platform_config

    def test_aws_platform_config_with_roles(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        aws_platform_body: kopf.Body,
        aws_platform_config: PlatformConfig,
    ) -> None:
        aws_platform_body["spec"]["iam"] = {
            "aws": {
                "region": "us-west-1",
                "roleArn": "role-arn",
                "s3RoleArn": "s3-role-arn",
            }
        }
        result = factory.create(aws_platform_body, cluster)

        assert result == replace(
            aws_platform_config,
            service_account_annotations={"eks.amazonaws.com/role-arn": "role-arn"},
            aws_region="us-west-1",
            aws_role_arn="role-arn",
            aws_s3_role_arn="s3-role-arn",
        )

    def test_aws_platform_config_without_registry__fails(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        aws_platform_body: kopf.Body,
    ) -> None:
        del aws_platform_body["spec"]["registry"]

        with pytest.raises(ValueError, match="Registry spec is empty"):
            factory.create(aws_platform_body, cluster)

    def test_azure_platform_config(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        azure_platform_body: kopf.Body,
        azure_platform_config: PlatformConfig,
    ) -> None:
        result = factory.create(azure_platform_body, cluster)

        assert result == azure_platform_config

    def test_azure_platform_config_without_registry__fails(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        azure_platform_body: kopf.Body,
    ) -> None:
        azure_platform_body["spec"]["registry"] = {}

        with pytest.raises(ValueError, match="Registry spec is empty"):
            factory.create(azure_platform_body, cluster)

    def test_platform_storage_overrides(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        gcp_platform_body: kopf.Body,
    ) -> None:
        gcp_platform_body["spec"]["platformStorage"] = {
            "helmValues": {
                "storages": [
                    {
                        "path": "/path",
                        "nfs": {"server": "nfs-server", "path": "/path"},
                    }
                ],
                "securityContext": {"enabled": True},
            }
        }

        result = factory.create(gcp_platform_body, cluster)

        assert result.platform_spec.platform_storage == PlatformStorageSpec(
            helm_values=PlatformStorageSpec.HelmValues(
                storages=[
                    PlatformStorageSpec.HelmValues.Storage(
                        path="/path",
                        nfs={"server": "nfs-server", "path": "/path"},
                    )
                ],
                securityContext={"enabled": True},
            )
        )

    def test_azure_platform_config_without_blob_storage__fails(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        azure_platform_body: kopf.Body,
    ) -> None:
        azure_platform_body["spec"]["blobStorage"] = {}

        with pytest.raises(ValueError, match="Blob storage spec is empty"):
            factory.create(azure_platform_body, cluster)

    def test_on_prem_platform_config(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        on_prem_platform_body: kopf.Body,
        on_prem_platform_config: PlatformConfig,
    ) -> None:
        result = factory.create(on_prem_platform_body, cluster)

        assert result == on_prem_platform_config

    def test_on_prem_platform_config_without_metrics(
        self,
        config: Config,
        cluster: Cluster,
        on_prem_platform_body: kopf.Body,
    ) -> None:
        config = replace(config, is_standalone=True)
        del on_prem_platform_body["spec"]["monitoring"]["metrics"]
        factory = PlatformConfigFactory(config)

        result = factory.create(on_prem_platform_body, cluster)

        assert result.monitoring.metrics_enabled is False

    def test_on_prem_platform_config_with_docker_registry_filesystem(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        on_prem_platform_body: kopf.Body,
    ) -> None:
        on_prem_platform_body["spec"]["registry"] = {
            "docker": {
                "url": "http://docker-registry",
                "username": "docker_username",
                "password": "docker_password",
            }
        }

        result = factory.create(on_prem_platform_body, cluster)

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
        cluster: Cluster,
        on_prem_platform_body: kopf.Body,
    ) -> None:
        on_prem_platform_body["spec"]["registry"] = {
            "docker": {"url": "http://docker-registry"}
        }

        result = factory.create(on_prem_platform_body, cluster)

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
        cluster: Cluster,
        on_prem_platform_body: kopf.Body,
    ) -> None:
        on_prem_platform_body["spec"]["registry"] = {
            "blobStorage": {
                "bucket": "job-images",
            }
        }

        result = factory.create(on_prem_platform_body, cluster)

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
        cluster: Cluster,
        on_prem_platform_body: kopf.Body,
    ) -> None:
        on_prem_platform_body["spec"]["blobStorage"] = {
            "minio": {
                "url": "http://minio",
                "region": "minio_region",
                "accessKey": "minio_access_key",
                "secretKey": "minio_secret_key",
            }
        }

        result = factory.create(on_prem_platform_body, cluster)

        assert result.buckets == BucketsConfig(
            provider=BucketsProvider.MINIO,
            minio_install=False,
            minio_url=URL("http://minio"),
            minio_public_url=URL(f"https://blob.{cluster.name}.org.neu.ro"),
            minio_region="minio_region",
            minio_access_key="minio_access_key",
            minio_secret_key="minio_secret_key",
        )

    def test_on_prem_platform_config_with_emc_ecs_buckets(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        on_prem_platform_body: kopf.Body,
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

        result = factory.create(on_prem_platform_body, cluster)

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
        cluster: Cluster,
        on_prem_platform_body: kopf.Body,
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

        result = factory.create(on_prem_platform_body, cluster)

        assert result.buckets == BucketsConfig(
            provider=BucketsProvider.OPEN_STACK,
            open_stack_username="account_id",
            open_stack_password="password",
            open_stack_s3_endpoint=URL("https://os.s3"),
            open_stack_endpoint=URL("https://os.management"),
            open_stack_region_name="region",
        )

    def test_on_prem_platform_config_with_custom_loki_dns_service(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        on_prem_platform_body: kopf.Body,
    ) -> None:
        on_prem_platform_body["spec"]["monitoring"]["logs"]["loki"] = {
            "dnsService": "custom-dns"
        }

        result = factory.create(on_prem_platform_body, cluster)

        assert result.monitoring.loki_dns_service == "custom-dns"

    def test_on_prem_platform_config_with_custom_loki_endpoint(
        self,
        factory: PlatformConfigFactory,
        cluster: Cluster,
        on_prem_platform_body: kopf.Body,
    ) -> None:
        on_prem_platform_body["spec"]["monitoring"]["logs"]["loki"] = {
            "enabled": False,
            "endpoint": "http://custom-loki-gateway.platform",
        }

        result = factory.create(on_prem_platform_body, cluster)

        assert not result.monitoring.loki_enabled
        assert result.monitoring.loki_endpoint == "http://custom-loki-gateway.platform"
