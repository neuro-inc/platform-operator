from dataclasses import replace
from ipaddress import AddressValueError, IPv4Address
from pathlib import Path
from typing import Any, Callable, Dict

import pytest
from kopf.structs import bodies
from yarl import URL

from platform_operator.models import (
    Cluster,
    Config,
    HelmChartNames,
    HelmChartVersions,
    HelmReleaseNames,
    HelmRepo,
    KubeClientAuthType,
    KubeConfig,
    LabelsConfig,
    PlatformConfig,
    PlatformConfigFactory,
)


class TestConfig:
    def test_config(self) -> None:
        env = {
            "NP_PLATFORM_AUTH_URL": "http://platformauthapi:8080",
            "NP_PLATFORM_CONFIG_URL": "http://platformconfig:8080",
            "NP_PLATFORM_API_URL": "http://platformapi:8080",
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
            "NP_HELM_STABLE_REPO_URL": (
                "https://kubernetes-charts.storage.googleapis.com"
            ),
            "NP_HELM_SERVICE_ACCOUNT_NAME": "default",
            "NP_HELM_PLATFORM_CHART_VERSION": "1.0.0",
            "NP_HELM_OBS_CSI_DRIVER_CHART_VERSION": "2.0.0",
            "NP_HELM_NFS_SERVER_CHART_VERSION": "3.0.0",
            "NP_PLATFORM_NAMESPACE": "platform",
            "NP_PLATFORM_JOBS_NAMESPACE": "platform-jobs",
        }
        assert Config.load_from_env(env) == Config(
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
            helm_stable_repo=HelmRepo(
                name="stable",
                url=URL("https://kubernetes-charts.storage.googleapis.com"),
            ),
            helm_release_names=HelmReleaseNames(
                platform="platform",
                obs_csi_driver="platform-obs-csi-driver",
                nfs_server="platform-nfs-server",
            ),
            helm_chart_names=HelmChartNames(),
            helm_chart_versions=HelmChartVersions(
                platform="1.0.0", obs_csi_driver="2.0.0", nfs_server="3.0.0"
            ),
            helm_service_account="default",
            platform_auth_url=URL("http://platformauthapi:8080"),
            platform_config_url=URL("http://platformconfig:8080"),
            platform_api_url=URL("http://platformapi:8080"),
            platform_namespace="platform",
            platform_jobs_namespace="platform-jobs",
            platform_consul_url=URL("http://platform-consul:8500"),
        )

    def test_config_defaults(self) -> None:
        env = {
            "NP_PLATFORM_AUTH_URL": "http://platformauthapi:8080",
            "NP_PLATFORM_CONFIG_URL": "http://platformconfig:8080",
            "NP_PLATFORM_API_URL": "http://platformapi:8080",
            "NP_KUBE_VERSION": "v1.14.10",
            "NP_KUBE_URL": "https://kubernetes.default",
            "NP_KUBE_AUTH_TYPE": "none",
            "NP_LABEL_JOB": "platform.neuromation.io/job",
            "NP_LABEL_NODE_POOL": "platform.neuromation.io/nodepool",
            "NP_LABEL_ACCELERATOR": "platform.neuromation.io/accelerator",
            "NP_LABEL_PREEMPTIBLE": "platform.neuromation.io/preemptible",
            "NP_HELM_STABLE_REPO_URL": (
                "https://kubernetes-charts.storage.googleapis.com"
            ),
            "NP_HELM_SERVICE_ACCOUNT_NAME": "default",
            "NP_HELM_PLATFORM_CHART_VERSION": "1.0.0",
            "NP_HELM_OBS_CSI_DRIVER_CHART_VERSION": "2.0.0",
            "NP_HELM_NFS_SERVER_CHART_VERSION": "3.0.0",
            "NP_PLATFORM_NAMESPACE": "platform",
            "NP_PLATFORM_JOBS_NAMESPACE": "platform-jobs",
        }
        assert Config.load_from_env(env) == Config(
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
            helm_stable_repo=HelmRepo(
                name="stable",
                url=URL("https://kubernetes-charts.storage.googleapis.com"),
            ),
            helm_release_names=HelmReleaseNames(
                platform="platform",
                obs_csi_driver="platform-obs-csi-driver",
                nfs_server="platform-nfs-server",
            ),
            helm_chart_names=HelmChartNames(),
            helm_chart_versions=HelmChartVersions(
                platform="1.0.0", obs_csi_driver="2.0.0", nfs_server="3.0.0"
            ),
            helm_service_account="default",
            platform_auth_url=URL("http://platformauthapi:8080"),
            platform_config_url=URL("http://platformconfig:8080"),
            platform_api_url=URL("http://platformapi:8080"),
            platform_namespace="platform",
            platform_jobs_namespace="platform-jobs",
            platform_consul_url=URL("http://platform-consul:8500"),
        )


class TestCluster:
    def test_name(self) -> None:
        cluster = Cluster({"name": "test"})

        assert cluster.name == "test"

    def test_cloud_provider_type(self) -> None:
        cluster = Cluster({"cloud_provider": {"type": "gcp"}})

        assert cluster.cloud_provider_type == "gcp"

    def test_acme_environment(self) -> None:
        cluster = Cluster({"ingress": {"acme_environment": "staging"}})

        assert cluster.acme_environment == "staging"

    def test_dns_zone_name(self) -> None:
        cluster = Cluster({"dns": {"zone_name": "test.org.neu.ro."}})

        assert cluster.dns_zone_name == "test.org.neu.ro."


class TestPlatformConfig:
    @pytest.fixture
    def traefik_service(self) -> Dict[str, Any]:
        return {
            "metadata": {"name", "platform-traefik"},
            "status": {"loadBalancer": {"ingress": [{"ip": "192.168.0.1"}]}},
        }

    @pytest.fixture
    def aws_traefik_service(self) -> Dict[str, Any]:
        return {
            "metadata": {"name", "platform-traefik"},
            "status": {"loadBalancer": {"ingress": [{"hostname": "traefik"}]}},
        }

    @pytest.fixture
    def aws_traefik_lb(self) -> Dict[str, Any]:
        return {
            "CanonicalHostedZoneNameID": "/hostedzone/traefik",
        }

    @pytest.fixture
    def service_account_secret(self) -> Dict[str, Any]:
        return {"data": {"ca.crt": "cert-authority-data", "token": "token"}}

    def test_create_dns_config(
        self, gcp_platform_config: PlatformConfig, traefik_service: Dict[str, Any]
    ) -> None:
        result = gcp_platform_config.create_dns_config(traefik_service=traefik_service)
        zone_name = gcp_platform_config.dns_zone_name

        assert result == {
            "zone_id": gcp_platform_config.dns_zone_id,
            "zone_name": gcp_platform_config.dns_zone_name,
            "name_servers": gcp_platform_config.dns_zone_name_servers,
            "a_records": [
                {"name": zone_name, "ips": ["192.168.0.1"]},
                {"name": f"*.jobs.{zone_name}", "ips": ["192.168.0.1"]},
                {"name": f"registry.{zone_name}", "ips": ["192.168.0.1"]},
                {"name": f"metrics.{zone_name}", "ips": ["192.168.0.1"]},
            ],
        }

    def test_create_on_prem_dns_config(
        self, on_prem_platform_config: PlatformConfig, traefik_service: Dict[str, Any]
    ) -> None:
        result = on_prem_platform_config.create_dns_config(
            traefik_service=traefik_service
        )
        zone_name = on_prem_platform_config.dns_zone_name

        assert result == {
            "zone_id": on_prem_platform_config.dns_zone_id,
            "zone_name": on_prem_platform_config.dns_zone_name,
            "name_servers": on_prem_platform_config.dns_zone_name_servers,
            "a_records": [
                {"name": zone_name, "ips": ["192.168.0.3"]},
                {"name": f"*.jobs.{zone_name}", "ips": ["192.168.0.3"]},
                {"name": f"registry.{zone_name}", "ips": ["192.168.0.3"]},
                {"name": f"metrics.{zone_name}", "ips": ["192.168.0.3"]},
            ],
        }

    def test_create_aws_dns_config(
        self,
        aws_platform_config: PlatformConfig,
        aws_traefik_service: Dict[str, Any],
        aws_traefik_lb: Dict[str, Any],
    ) -> None:
        result = aws_platform_config.create_dns_config(
            traefik_service=aws_traefik_service, aws_traefik_lb=aws_traefik_lb
        )
        zone_name = aws_platform_config.dns_zone_name

        assert result == {
            "zone_id": aws_platform_config.dns_zone_id,
            "zone_name": aws_platform_config.dns_zone_name,
            "name_servers": aws_platform_config.dns_zone_name_servers,
            "a_records": [
                {
                    "name": zone_name,
                    "dns_name": "traefik",
                    "zone_id": "/hostedzone/traefik",
                },
                {
                    "name": f"*.jobs.{zone_name}",
                    "dns_name": "traefik",
                    "zone_id": "/hostedzone/traefik",
                },
                {
                    "name": f"registry.{zone_name}",
                    "dns_name": "traefik",
                    "zone_id": "/hostedzone/traefik",
                },
                {
                    "name": f"metrics.{zone_name}",
                    "dns_name": "traefik",
                    "zone_id": "/hostedzone/traefik",
                },
            ],
        }

    def test_create_cluster_config(
        self,
        cluster_name: str,
        gcp_platform_config: PlatformConfig,
        service_account_secret: Dict[str, Any],
        traefik_service: Dict[str, Any],
        resource_pool_type_factory: Callable[[str], Dict[str, Any]],
        resource_preset_factory: Callable[[], Dict[str, Any]],
    ) -> None:
        resource_preset = resource_preset_factory()
        resource_preset.pop("resource_affinity", None)

        result = gcp_platform_config.create_cluster_config(
            service_account_secret=service_account_secret,
            traefik_service=traefik_service,
        )
        zone_name = gcp_platform_config.dns_zone_name

        assert result == {
            "storage": {
                "url": f"https://{cluster_name}.org.neu.ro/api/v1/storage",
                "pvc": {"name": "platform-storage"},
            },
            "orchestrator": {
                "kubernetes": {
                    "url": "https://kubernetes.default",
                    "ca_data": "cert-authority-data",
                    "auth_type": "token",
                    "token": "token",
                    "namespace": "platform-jobs",
                    "node_label_gpu": "platform.neuromation.io/accelerator",
                    "node_label_preemptible": "platform.neuromation.io/preemptible",
                    "node_label_job": "platform.neuromation.io/job",
                    "node_label_node_pool": "platform.neuromation.io/nodepool",
                    "job_pod_priority_class_name": "platform-job",
                },
                "is_http_ingress_secure": True,
                "job_hostname_template": f"{{job_id}}.jobs.{cluster_name}.org.neu.ro",
                "job_fallback_hostname": "default.jobs-dev.neu.ro",
                "job_schedule_timeout_s": 60,
                "job_schedule_scale_up_timeout_s": 30,
                "resource_pool_types": [resource_pool_type_factory("192.168.0.0/16")],
                "resource_presets": [resource_preset],
            },
            "dns": {
                "zone_id": gcp_platform_config.dns_zone_id,
                "zone_name": gcp_platform_config.dns_zone_name,
                "name_servers": gcp_platform_config.dns_zone_name_servers,
                "a_records": [
                    {"name": zone_name, "ips": ["192.168.0.1"]},
                    {"name": f"*.jobs.{zone_name}", "ips": ["192.168.0.1"]},
                    {"name": f"registry.{zone_name}", "ips": ["192.168.0.1"]},
                    {"name": f"metrics.{zone_name}", "ips": ["192.168.0.1"]},
                ],
            },
        }

    def test_create_cluster_config_without_traefik_service(
        self,
        gcp_platform_config: PlatformConfig,
        service_account_secret: Dict[str, Any],
    ) -> None:
        result = gcp_platform_config.create_cluster_config(
            service_account_secret=service_account_secret,
        )

        assert "dns" not in result

    def test_create_azure_cluster_config(
        self,
        azure_platform_config: PlatformConfig,
        service_account_secret: Dict[str, Any],
        traefik_service: Dict[str, Any],
    ) -> None:
        result = azure_platform_config.create_cluster_config(
            service_account_secret=service_account_secret,
            traefik_service=traefik_service,
        )
        assert (
            result["orchestrator"]["kubernetes"]["job_pod_preemptible_toleration_key"]
            == "kubernetes.azure.com/scalesetpriority"
        )


class TestPlatformConfigFactory:
    @pytest.fixture
    def factory(self, config: Config) -> PlatformConfigFactory:
        return PlatformConfigFactory(config)

    def test_platform_config_without_kubernetes_public_url__fails(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: bodies.Body,
        gcp_cluster: Cluster,
    ) -> None:
        del gcp_platform_body["spec"]["kubernetes"]["publicUrl"]

        with pytest.raises(KeyError):
            factory.create(gcp_platform_body, gcp_cluster)

    def test_platform_config_with_custom_labels(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: bodies.Body,
        gcp_cluster: Cluster,
    ) -> None:
        gcp_platform_body["spec"]["kubernetes"]["nodeLabels"] = {
            "job": "job",
            "nodePool": "nodepool",
            "accelerator": "accelerator",
            "preemptible": "preemptible",
        }

        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result.kubernetes_node_labels == LabelsConfig(
            job="job",
            node_pool="nodepool",
            accelerator="accelerator",
            preemptible="preemptible",
        )

    def test_gcp_platform_config(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: bodies.Body,
        gcp_cluster: Cluster,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result == gcp_platform_config

    def test_gcp_platform_config_without_tpu(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: bodies.Body,
        gcp_cluster: Cluster,
        gcp_platform_config: PlatformConfig,
        resource_pool_type_factory: Callable[[], Dict[str, Any]],
    ) -> None:
        del gcp_platform_body["spec"]["kubernetes"]["tpuIPv4CIDR"]
        gcp_cluster["orchestrator"]["resource_pool_types"] = [
            resource_pool_type_factory()
        ]
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result == replace(
            gcp_platform_config,
            jobs_resource_pool_types=[resource_pool_type_factory()],
        )

    def test_gcp_platform_config_without_service_account_key_in_spec(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: bodies.Body,
        gcp_cluster: Cluster,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        del gcp_platform_body["spec"]["iam"]["gcp"]["serviceAccountKeyBase64"]
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result == replace(
            gcp_platform_config,
            gcp=replace(
                gcp_platform_config.gcp,
                service_account_key=(
                    '{"client_email": "test-acc@test-project.iam.gserviceaccount.com"}'
                ),
                service_account_key_base64=(
                    "eyJjbGllbnRfZW1haWwiOiAidGVzdC1hY2NAdGV"
                    "zdC1wcm9qZWN0LmlhbS5nc2VydmljZWFjY291bnQuY29tIn0="
                ),
            ),
        )

    def test_gcp_platform_config_without_service_account_key___fails(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: bodies.Body,
        gcp_cluster: Cluster,
    ) -> None:
        del gcp_platform_body["spec"]["iam"]["gcp"]["serviceAccountKeyBase64"]
        del gcp_cluster["cloud_provider"]["credentials"]

        with pytest.raises(KeyError):
            factory.create(gcp_platform_body, gcp_cluster)

    def test_gcp_platform_config_with_gcs_storage(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: bodies.Body,
        gcp_cluster: Cluster,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        gcp_platform_body["spec"]["storage"] = {"gcs": {"bucket": "platform-storage"}}
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result == replace(
            gcp_platform_config,
            gcp=replace(
                gcp_platform_config.gcp,
                storage_type="gcs",
                storage_gcs_bucket_name="platform-storage",
                storage_nfs_server="",
                storage_nfs_path="/",
            ),
        )

    def test_gcp_platform_config_without_storage___fails(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: bodies.Body,
        gcp_cluster: Cluster,
    ) -> None:
        gcp_platform_body["spec"]["storage"] = {}

        with pytest.raises(AssertionError):
            factory.create(gcp_platform_body, gcp_cluster)

    def test_gcp_platform_config_with_ingress_controller_disabled(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: bodies.Body,
        gcp_cluster: Cluster,
        gcp_platform_config: PlatformConfig,
    ) -> None:
        gcp_platform_body["spec"]["kubernetes"]["ingressController"] = {
            "enabled": False
        }
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result == replace(gcp_platform_config, ingress_controller_enabled=False)

    def test_gcp_platform_config_with_custom_docker_config_secret(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: bodies.Body,
        gcp_cluster: Cluster,
    ) -> None:
        gcp_platform_body["spec"]["kubernetes"]["dockerConfigSecret"] = {
            "create": False,
            "name": "secret",
        }
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result.docker_config_secret_create is False
        assert result.docker_config_secret_name == "secret"
        assert result.image_pull_secret_names == ["secret"]

    def test_gcp_platform_config_with_service_account_image_pull_secrets(
        self,
        factory: PlatformConfigFactory,
        gcp_platform_body: bodies.Body,
        gcp_cluster: Cluster,
    ) -> None:
        gcp_platform_body["spec"]["kubernetes"]["serviceAccount"] = {
            "imagePullSecrets": [{"name": "secret"}, {"name": "platform-docker-config"}]
        }
        result = factory.create(gcp_platform_body, gcp_cluster)

        assert result.image_pull_secret_names == ["secret", "platform-docker-config"]

    def test_aws_platform_config(
        self,
        factory: PlatformConfigFactory,
        aws_platform_body: bodies.Body,
        aws_cluster: Cluster,
        aws_platform_config: PlatformConfig,
    ) -> None:
        result = factory.create(aws_platform_body, aws_cluster)

        assert result == aws_platform_config

    def test_aws_platform_config_with_roles(
        self,
        factory: PlatformConfigFactory,
        aws_platform_body: bodies.Body,
        aws_cluster: Cluster,
        aws_platform_config: PlatformConfig,
    ) -> None:
        aws_platform_body["spec"]["iam"] = {"aws": {"roleArn": "role_arn"}}
        result = factory.create(aws_platform_body, aws_cluster)

        assert result == replace(
            aws_platform_config,
            aws=replace(
                aws_platform_config.aws,
                role_arn="role_arn",
            ),
        )

    def test_aws_platform_config_without_registry__fails(
        self,
        factory: PlatformConfigFactory,
        aws_platform_body: bodies.Body,
        aws_cluster: Cluster,
        aws_platform_config: PlatformConfig,
    ) -> None:
        del aws_platform_body["spec"]["registry"]

        with pytest.raises(KeyError):
            factory.create(aws_platform_body, aws_cluster)

    def test_aws_platform_config_without_storage__fails(
        self,
        factory: PlatformConfigFactory,
        aws_platform_body: bodies.Body,
        aws_cluster: Cluster,
        aws_platform_config: PlatformConfig,
    ) -> None:
        aws_platform_body["spec"]["storage"] = {}

        with pytest.raises(KeyError):
            factory.create(aws_platform_body, aws_cluster)

    def test_azure_platform_config(
        self,
        factory: PlatformConfigFactory,
        azure_platform_body: bodies.Body,
        azure_cluster: Cluster,
        azure_platform_config: PlatformConfig,
    ) -> None:
        result = factory.create(azure_platform_body, azure_cluster)

        assert result == azure_platform_config

    def test_azure_platform_config_without_registry__fails(
        self,
        factory: PlatformConfigFactory,
        azure_platform_body: bodies.Body,
        azure_cluster: Cluster,
        azure_platform_config: PlatformConfig,
    ) -> None:
        azure_platform_body["spec"]["registry"] = {}

        with pytest.raises(KeyError):
            factory.create(azure_platform_body, azure_cluster)

    def test_azure_platform_config_without_storage__fails(
        self,
        factory: PlatformConfigFactory,
        azure_platform_body: bodies.Body,
        azure_cluster: Cluster,
        azure_platform_config: PlatformConfig,
    ) -> None:
        azure_platform_body["spec"]["storage"] = {}

        with pytest.raises(KeyError):
            factory.create(azure_platform_body, azure_cluster)

    def test_azure_platform_config_without_blob_storage__fails(
        self,
        factory: PlatformConfigFactory,
        azure_platform_body: bodies.Body,
        azure_cluster: Cluster,
        azure_platform_config: PlatformConfig,
    ) -> None:
        azure_platform_body["spec"]["blobStorage"] = {}

        with pytest.raises(KeyError):
            factory.create(azure_platform_body, azure_cluster)

    def test_on_prem_platform_config(
        self,
        factory: PlatformConfigFactory,
        on_prem_platform_body: bodies.Body,
        on_prem_cluster: Cluster,
        on_prem_platform_config: PlatformConfig,
    ) -> None:
        result = factory.create(on_prem_platform_body, on_prem_cluster)

        assert result == on_prem_platform_config

    def test_on_prem_platform_config_with_public_ip_from_kubernetes_public_url(
        self,
        factory: PlatformConfigFactory,
        on_prem_platform_body: bodies.Body,
        on_prem_cluster: Cluster,
    ) -> None:
        del on_prem_platform_body["spec"]["kubernetes"]["publicIP"]
        on_prem_platform_body["spec"]["kubernetes"][
            "publicUrl"
        ] = "https://192.168.0.1:6443"
        result = factory.create(on_prem_platform_body, on_prem_cluster)

        assert result.on_prem
        assert result.on_prem.kubernetes_public_ip == IPv4Address("192.168.0.1")

    def test_on_prem_platform_config_without_public_ip__fails(
        self,
        factory: PlatformConfigFactory,
        on_prem_platform_body: bodies.Body,
        on_prem_cluster: Cluster,
    ) -> None:
        del on_prem_platform_body["spec"]["kubernetes"]["publicIP"]
        on_prem_platform_body["spec"]["kubernetes"][
            "publicUrl"
        ] = "https://kubernetes:6443"

        with pytest.raises(AddressValueError):
            factory.create(on_prem_platform_body, on_prem_cluster)

    def test_on_prem_platform_config_with_default_persistence_sizes(
        self,
        factory: PlatformConfigFactory,
        on_prem_platform_body: bodies.Body,
        on_prem_cluster: Cluster,
    ) -> None:
        del on_prem_platform_body["spec"]["registry"]["kubernetes"]["persistence"][
            "size"
        ]
        del on_prem_platform_body["spec"]["storage"]["kubernetes"]["persistence"][
            "size"
        ]
        result = factory.create(on_prem_platform_body, on_prem_cluster)

        assert result.on_prem
        assert result.on_prem.registry_storage_size == "10Gi"

    def test_on_prem_platform_config_without_node_ports__fails(
        self,
        factory: PlatformConfigFactory,
        on_prem_platform_body: bodies.Body,
        on_prem_cluster: Cluster,
        on_prem_platform_config: PlatformConfig,
    ) -> None:
        del on_prem_platform_body["spec"]["kubernetes"]["nodePorts"]

        with pytest.raises(KeyError):
            factory.create(on_prem_platform_body, on_prem_cluster)
