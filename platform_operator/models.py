from __future__ import annotations

import os
from base64 import b64decode
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path
from typing import Any

import kopf
from neuro_config_client import (
    ACMEEnvironment,
    ARecord,
    Cluster,
    DNSConfig,
    DockerRegistryConfig,
    IdleJobConfig,
    OrchestratorConfig,
    ResourcePoolType,
)
from yarl import URL


@dataclass(frozen=True)
class Certificate:
    private_key: str
    certificate: str


class KubeClientAuthType(str, Enum):
    NONE = "none"
    TOKEN = "token"
    CERTIFICATE = "certificate"


@dataclass(frozen=True)
class KubeConfig:
    version: str
    url: URL
    cert_authority_path: Path | None = None
    cert_authority_data_pem: str | None = None
    auth_type: KubeClientAuthType = KubeClientAuthType.NONE
    auth_cert_path: Path | None = None
    auth_cert_key_path: Path | None = None
    auth_token: str | None = None
    auth_token_path: Path | None = None
    auth_token_update_interval_s: int = 300
    conn_timeout_s: int = 300
    read_timeout_s: int = 100
    conn_pool_size: int = 100

    @classmethod
    def load_from_env(cls, env: Mapping[str, str] | None = None) -> KubeConfig:
        env = env or os.environ
        return cls(
            version=env["NP_KUBE_VERSION"].lstrip("v"),
            url=URL(env["NP_KUBE_URL"]),
            cert_authority_path=cls._convert_to_path(
                env.get("NP_KUBE_CERT_AUTHORITY_PATH")
            ),
            cert_authority_data_pem=env.get("NP_KUBE_CERT_AUTHORITY_DATA_PEM"),
            auth_type=KubeClientAuthType(env["NP_KUBE_AUTH_TYPE"]),
            auth_cert_path=cls._convert_to_path(env.get("NP_KUBE_AUTH_CERT_PATH")),
            auth_cert_key_path=cls._convert_to_path(
                env.get("NP_KUBE_AUTH_CERT_KEY_PATH")
            ),
            auth_token_path=cls._convert_to_path(env.get("NP_KUBE_AUTH_TOKEN_PATH")),
            auth_token=env.get("NP_KUBE_AUTH_TOKEN"),
        )

    @classmethod
    def _convert_to_path(cls, value: str | None) -> Path | None:
        return Path(value) if value else None


@dataclass(frozen=True)
class LabelsConfig:
    job: str = "platform.neuromation.io/job"
    node_pool: str = "platform.neuromation.io/nodepool"
    accelerator: str = "platform.neuromation.io/accelerator"
    preemptible: str = "platform.neuromation.io/preemptible"


@dataclass(frozen=True)
class HelmRepo:
    url: URL
    name: str = ""
    username: str = ""
    password: str = ""


@dataclass
class HelmReleaseNames:
    platform: str


@dataclass(frozen=True)
class HelmChartNames:
    docker_registry: str = "docker-registry"
    minio: str = "minio"
    traefik: str = "traefik"
    adjust_inotify: str = "adjust-inotify"
    nvidia_gpu_driver: str = "nvidia-gpu-driver"
    nvidia_gpu_driver_gcp: str = "nvidia-gpu-driver-gcp"
    platform: str = "platform"
    platform_storage: str = "platform-storage"
    platform_registry: str = "platform-registry"
    platform_monitoring: str = "platform-monitoring"
    platform_container_runtime: str = "platform-container-runtime"
    platform_secrets: str = "platform-secrets"
    platform_reports: str = "platform-reports"
    platform_disks: str = "platform-disks"
    platform_api_poller: str = "platform-api-poller"
    platform_buckets: str = "platform-buckets"
    platform_apps: str = "platform-apps"


@dataclass(frozen=True)
class HelmChartVersions:
    platform: str


@dataclass(frozen=True)
class Config:
    node_name: str
    log_level: str
    retries: int
    backoff: int
    kube_config: KubeConfig
    helm_release_names: HelmReleaseNames
    helm_chart_names: HelmChartNames
    helm_chart_versions: HelmChartVersions
    platform_auth_url: URL
    platform_ingress_auth_url: URL
    platform_config_url: URL
    platform_admin_url: URL
    platform_config_watch_interval_s: float
    platform_api_url: URL
    platform_notifications_url: URL
    platform_namespace: str
    platform_lock_secret_name: str
    acme_ca_staging_path: str
    is_standalone: bool

    @classmethod
    def load_from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        env = env or os.environ
        return cls(
            node_name=env["NP_NODE_NAME"],
            log_level=(env.get("NP_CONTROLLER_LOG_LEVEL") or "INFO").upper(),
            retries=int(env.get("NP_CONTROLLER_RETRIES") or "3"),
            backoff=int(env.get("NP_CONTROLLER_BACKOFF") or "60"),
            kube_config=KubeConfig.load_from_env(env),
            helm_release_names=HelmReleaseNames(platform="platform"),
            helm_chart_names=HelmChartNames(),
            helm_chart_versions=HelmChartVersions(
                platform=env["NP_HELM_PLATFORM_CHART_VERSION"],
            ),
            platform_auth_url=URL(env["NP_PLATFORM_AUTH_URL"]),
            platform_ingress_auth_url=URL(env["NP_PLATFORM_INGRESS_AUTH_URL"]),
            platform_config_url=URL(env["NP_PLATFORM_CONFIG_URL"]),
            platform_admin_url=URL(env["NP_PLATFORM_ADMIN_URL"]),
            platform_config_watch_interval_s=float(
                env.get("NP_PLATFORM_CONFIG_WATCH_INTERVAL_S", "15")
            ),
            platform_api_url=URL(env["NP_PLATFORM_API_URL"]),
            platform_notifications_url=URL(env["NP_PLATFORM_NOTIFICATIONS_URL"]),
            platform_namespace=env["NP_PLATFORM_NAMESPACE"],
            platform_lock_secret_name=env["NP_PLATFORM_LOCK_SECRET_NAME"],
            acme_ca_staging_path=env["NP_ACME_CA_STAGING_PATH"],
            is_standalone=env.get("NP_STANDALONE", "false").lower() == "true",
        )


def _spec_default_factory() -> dict[str, Any]:
    return defaultdict(_spec_default_factory)


class IamSpec(dict[str, Any]):
    def __init__(self, spec: dict[str, Any]) -> None:
        super().__init__(spec)

        self._spec = defaultdict(_spec_default_factory, spec)

    @property
    def aws_region(self) -> str:
        return self._spec["aws"].get("region", "")

    @property
    def aws_role_arn(self) -> str:
        return self._spec["aws"].get("roleArn", "")

    @property
    def aws_s3_role_arn(self) -> str:
        return self._spec["aws"].get("s3RoleArn", "")

    @property
    def gcp_service_account_key_base64(self) -> str:
        return self._spec["gcp"].get("serviceAccountKeyBase64", "")


class KubernetesSpec(dict[str, Any]):
    def __init__(self, spec: dict[str, Any]) -> None:
        super().__init__(spec)

        self._spec = defaultdict(_spec_default_factory, spec)

    @property
    def provider(self) -> str:
        return self["provider"]

    @property
    def standard_storage_class_name(self) -> str:
        return self.get("standardStorageClassName", "")

    @property
    def node_label_job(self) -> str:
        return self._spec["nodeLabels"].get("job", "")

    @property
    def node_label_node_pool(self) -> str:
        return self._spec["nodeLabels"].get("nodePool", "")

    @property
    def node_label_accelerator(self) -> str:
        return self._spec["nodeLabels"].get("accelerator", "")

    @property
    def node_label_preemptible(self) -> str:
        return self._spec["nodeLabels"].get("preemptible", "")

    @property
    def kubelet_port(self) -> int | None:
        return self.get("kubeletPort")

    @property
    def docker_config_secret_create(self) -> bool:
        return self._spec["dockerConfigSecret"].get("create", True)

    @property
    def docker_config_secret_name(self) -> str:
        return self._spec["dockerConfigSecret"].get("name", "")

    @property
    def tpu_network(self) -> IPv4Network | None:
        return IPv4Network(self["tpuIPv4CIDR"]) if self.get("tpuIPv4CIDR") else None


class StorageSpec(dict[str, Any]):
    def __init__(self, spec: dict[str, Any]) -> None:
        super().__init__(spec)

    @property
    def path(self) -> str:
        return self.get("path", "")

    @property
    def storage_size(self) -> str:
        return self["kubernetes"]["persistence"].get("size", "")

    @property
    def storage_class_name(self) -> str:
        return self["kubernetes"]["persistence"].get("storageClassName", "")

    @property
    def nfs_server(self) -> str:
        return self["nfs"].get("server", "")

    @property
    def nfs_export_path(self) -> str:
        return self["nfs"].get("path", "/")

    @property
    def smb_server(self) -> str:
        return self["smb"].get("server", "")

    @property
    def smb_share_name(self) -> str:
        return self["smb"].get("shareName", "")

    @property
    def smb_username(self) -> str:
        return self["smb"].get("username", "")

    @property
    def smb_password(self) -> str:
        return self["smb"].get("password", "")

    @property
    def gcs_bucket_name(self) -> str:
        return self["gcs"].get("bucket", "")

    @property
    def azure_storage_account_name(self) -> str:
        return self["azureFile"].get("storageAccountName", "")

    @property
    def azure_storage_account_key(self) -> str:
        return self["azureFile"].get("storageAccountKey", "")

    @property
    def azure_share_name(self) -> str:
        return self["azureFile"].get("shareName", "")


class BlobStorageSpec(dict[str, Any]):
    def __init__(self, spec: dict[str, Any]) -> None:
        super().__init__(spec)

    @property
    def aws_region(self) -> str:
        return self["aws"]["region"]

    @property
    def gcp_project(self) -> str:
        return self["gcp"]["project"]

    @property
    def azure_storrage_account_name(self) -> str:
        return self["azure"]["storageAccountName"]

    @property
    def azure_storrage_account_key(self) -> str:
        return self["azure"]["storageAccountKey"]

    @property
    def emc_ecs_access_key_id(self) -> str:
        return self["emcEcs"]["accessKeyId"]

    @property
    def emc_ecs_secret_access_key(self) -> str:
        return self["emcEcs"]["secretAccessKey"]

    @property
    def emc_ecs_s3_role(self) -> str:
        return self["emcEcs"]["s3Role"]

    @property
    def emc_ecs_s3_endpoint(self) -> str:
        return self["emcEcs"]["s3Endpoint"]

    @property
    def emc_ecs_management_endpoint(self) -> str:
        return self["emcEcs"]["managementEndpoint"]

    @property
    def open_stack_region(self) -> str:
        return self["openStack"]["region"]

    @property
    def open_stack_username(self) -> str:
        return self["openStack"]["username"]

    @property
    def open_stack_password(self) -> str:
        return self["openStack"]["password"]

    @property
    def open_stack_endpoint(self) -> str:
        return self["openStack"]["endpoint"]

    @property
    def open_stack_s3_endpoint(self) -> str:
        return self["openStack"]["s3Endpoint"]

    @property
    def minio_url(self) -> str:
        return self["minio"]["url"]

    @property
    def minio_region(self) -> str:
        return self["minio"]["region"]

    @property
    def minio_access_key(self) -> str:
        return self["minio"]["accessKey"]

    @property
    def minio_secret_key(self) -> str:
        return self["minio"]["secretKey"]

    @property
    def kubernetes_storage_class_name(self) -> str:
        return self["kubernetes"]["persistence"].get("storageClassName", "")

    @property
    def kubernetes_storage_size(self) -> str:
        return self["kubernetes"]["persistence"].get("size", "")


class RegistrySpec(dict[str, Any]):
    def __init__(self, spec: dict[str, Any]) -> None:
        super().__init__(spec)

    @property
    def aws_account_id(self) -> str:
        return self["aws"]["accountId"]

    @property
    def aws_region(self) -> str:
        return self["aws"]["region"]

    @property
    def gcp_project(self) -> str:
        return self["gcp"]["project"]

    @property
    def azure_url(self) -> str:
        return self["azure"]["url"]

    @property
    def azure_username(self) -> str:
        return self["azure"]["username"]

    @property
    def azure_password(self) -> str:
        return self["azure"]["password"]

    @property
    def docker_url(self) -> str:
        return self["docker"]["url"]

    @property
    def docker_username(self) -> str:
        return self["docker"].get("username", "")

    @property
    def docker_password(self) -> str:
        return self["docker"].get("password", "")

    @property
    def kubernetes_storage_class_name(self) -> str:
        return self["kubernetes"]["persistence"].get("storageClassName", "")

    @property
    def kubernetes_storage_size(self) -> str:
        return self["kubernetes"]["persistence"].get("size", "")


class MonitoringSpec(dict[str, Any]):
    def __init__(self, spec: dict[str, Any]) -> None:
        super().__init__(spec)

    @property
    def logs_region(self) -> str:
        return self["logs"]["blobStorage"].get("region", "")

    @property
    def logs_bucket(self) -> str:
        return self["logs"]["blobStorage"]["bucket"]

    @property
    def metrics(self) -> dict[str, Any]:
        return self["metrics"]

    @property
    def metrics_region(self) -> str:
        return self["metrics"].get("region", "")

    @property
    def metrics_retention_time(self) -> str:
        return self["metrics"].get("retentionTime", "")

    @property
    def metrics_bucket(self) -> str:
        return self["metrics"]["blobStorage"].get("bucket", "")

    @property
    def metrics_storage_size(self) -> str:
        return self["metrics"]["kubernetes"]["persistence"].get("size", "")

    @property
    def metrics_storage_class_name(self) -> str:
        return self["metrics"]["kubernetes"]["persistence"].get("storageClassName", "")


class DisksSpec(dict[str, Any]):
    def __init__(self, spec: dict[str, Any]) -> None:
        super().__init__(spec)

        self._spec = defaultdict(_spec_default_factory, spec)

    @property
    def storage_class_name(self) -> str:
        return self._spec["kubernetes"]["persistence"].get("storageClassName", "")


class IngressControllerSpec(dict[str, Any]):
    def __init__(self, spec: dict[str, Any]) -> None:
        super().__init__(spec)

        self._spec = defaultdict(_spec_default_factory, spec)

    @property
    def enabled(self) -> bool:
        return self._spec.get("enabled", True)

    @property
    def replicas(self) -> int | None:
        return self._spec.get("replicas")

    @property
    def namespaces(self) -> Sequence[str]:
        return self._spec.get("namespaces", ())

    @property
    def service_type(self) -> str:
        return self._spec.get("serviceType", "")

    @property
    def service_annotations(self) -> dict[str, str]:
        return self._spec.get("serviceAnnotations", {})

    @property
    def load_balancer_source_ranges(self) -> list[str]:
        return self._spec.get("loadBalancerSourceRanges", [])

    @property
    def public_ips(self) -> Sequence[IPv4Address]:
        return [IPv4Address(ip) for ip in self._spec.get("publicIPs", [])]

    @property
    def node_port_http(self) -> int | None:
        return self._spec["nodePorts"].get("http")

    @property
    def node_port_https(self) -> int | None:
        return self._spec["nodePorts"].get("https")

    @property
    def host_port_http(self) -> int | None:
        return self._spec["hostPorts"].get("http")

    @property
    def host_port_https(self) -> int | None:
        return self._spec["hostPorts"].get("https")

    @property
    def ssl_cert_data(self) -> str:
        return self._spec["ssl"].get("certificateData", "")

    @property
    def ssl_cert_key_data(self) -> str:
        return self._spec["ssl"].get("certificateKeyData", "")


class Spec(dict[str, Any]):
    def __init__(self, spec: dict[str, Any]) -> None:
        super().__init__(spec)

        spec = defaultdict(_spec_default_factory, spec)
        self._token = spec.get("token", "")
        self._iam = IamSpec(spec["iam"])
        self._kubernetes = KubernetesSpec(spec["kubernetes"])
        self._ingress_controller = IngressControllerSpec(spec["ingressController"])
        self._registry = RegistrySpec(spec["registry"])
        self._storages = [StorageSpec(s) for s in spec["storages"]]
        self._blob_storage = BlobStorageSpec(spec["blobStorage"])
        self._disks = DisksSpec(spec["disks"])
        self._monitoring = MonitoringSpec(spec["monitoring"])

    @property
    def token(self) -> str:
        return self._token

    @property
    def iam(self) -> IamSpec:
        return self._iam

    @property
    def kubernetes(self) -> KubernetesSpec:
        return self._kubernetes

    @property
    def ingress_controller(self) -> IngressControllerSpec:
        return self._ingress_controller

    @property
    def registry(self) -> RegistrySpec:
        return self._registry

    @property
    def storages(self) -> Sequence[StorageSpec]:
        return self._storages

    @property
    def blob_storage(self) -> BlobStorageSpec:
        return self._blob_storage

    @property
    def disks(self) -> DisksSpec:
        return self._disks

    @property
    def monitoring(self) -> MonitoringSpec:
        return self._monitoring


class Metadata(dict[str, Any]):
    def __init__(self, spec: dict[str, Any]) -> None:
        super().__init__(spec)

    @property
    def name(self) -> str:
        return self["name"]


@dataclass(frozen=True)
class DockerConfig:
    url: URL
    email: str = ""
    username: str = ""
    password: str = ""
    secret_name: str = ""
    create_secret: bool = False


class IngressServiceType(str, Enum):
    LOAD_BALANCER = "LoadBalancer"
    NODE_PORT = "NodePort"


class StorageType(str, Enum):
    KUBERNETES = "kubernetes"
    NFS = "nfs"
    SMB = "smb"
    GCS = "gcs"
    AZURE_fILE = "azureFile"


@dataclass(frozen=True)
class StorageConfig:
    type: StorageType
    path: str = ""
    storage_size: str = "10Gi"
    storage_class_name: str = ""
    nfs_export_path: str = ""
    nfs_server: str = ""
    smb_server: str = ""
    smb_share_name: str = ""
    smb_username: str = ""
    smb_password: str = ""
    azure_storage_account_name: str = ""
    azure_storage_account_key: str = ""
    azure_share_name: str = ""
    gcs_bucket_name: str = ""


class RegistryProvider(str, Enum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    DOCKER = "docker"


@dataclass(frozen=True)
class RegistryConfig:
    provider: RegistryProvider

    aws_account_id: str = ""
    aws_region: str = ""

    gcp_project: str = ""

    azure_url: URL | None = None
    azure_username: str = ""
    azure_password: str = ""

    docker_registry_install: bool = False
    docker_registry_url: URL | None = None
    docker_registry_username: str = ""
    docker_registry_password: str = ""
    docker_registry_storage_class_name: str = ""
    docker_registry_storage_size: str = ""


class BucketsProvider(str, Enum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    EMC_ECS = "emcEcs"
    OPEN_STACK = "openStack"
    MINIO = "minio"


@dataclass(frozen=True)
class BucketsConfig:
    provider: BucketsProvider
    disable_creation: bool = False

    aws_region: str = ""

    gcp_project: str = ""
    gcp_location: str = "us"  # default GCP location

    azure_storage_account_name: str = ""
    azure_storage_account_key: str = ""

    minio_install: bool = False
    minio_url: URL | None = None
    minio_public_url: URL | None = None
    minio_region: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_storage_class_name: str = ""
    minio_storage_size: str = ""

    emc_ecs_access_key_id: str = ""
    emc_ecs_secret_access_key: str = ""
    emc_ecs_s3_endpoint: URL | None = None
    emc_ecs_management_endpoint: URL | None = None
    emc_ecs_s3_assumable_role: str = ""

    open_stack_username: str = ""
    open_stack_password: str = ""
    open_stack_endpoint: URL | None = None
    open_stack_s3_endpoint: URL | None = None
    open_stack_region_name: str = ""


class MetricsStorageType(Enum):
    BUCKETS = 1
    KUBERNETES = 2


@dataclass(frozen=True)
class MonitoringConfig:
    logs_bucket_name: str
    logs_region: str = ""
    metrics_enabled: bool = True
    metrics_storage_type: MetricsStorageType = MetricsStorageType.BUCKETS
    metrics_bucket_name: str = ""
    metrics_storage_class_name: str = ""
    metrics_storage_size: str = ""
    metrics_retention_time: str = "3d"
    metrics_region: str = ""


@dataclass(frozen=True)
class PlatformConfig:
    release_name: str
    auth_url: URL
    ingress_auth_url: URL
    config_url: URL
    admin_url: URL
    api_url: URL
    notifications_url: URL
    token: str
    cluster_name: str
    service_account_name: str
    service_account_annotations: dict[str, str]
    image_pull_secret_names: Sequence[str]
    pre_pull_images: Sequence[str]
    standard_storage_class_name: str | None
    kubernetes_provider: str
    kubernetes_version: str
    kubernetes_tpu_network: IPv4Network | None
    node_labels: LabelsConfig
    kubelet_port: int
    nvidia_dcgm_port: int
    namespace: str
    ingress_dns_name: str
    ingress_url: URL
    ingress_registry_url: URL
    ingress_metrics_url: URL
    ingress_acme_enabled: bool
    ingress_acme_environment: ACMEEnvironment
    ingress_controller_install: bool
    ingress_controller_replicas: int
    ingress_public_ips: Sequence[IPv4Address]
    ingress_cors_origins: Sequence[str]
    ingress_node_port_http: int | None
    ingress_node_port_https: int | None
    ingress_host_port_http: int | None
    ingress_host_port_https: int | None
    ingress_service_type: IngressServiceType
    ingress_service_name: str
    ingress_service_annotations: dict[str, str]
    ingress_load_balancer_source_ranges: list[str]
    ingress_ssl_cert_data: str
    ingress_ssl_cert_key_data: str
    disks_storage_limit_per_user: int
    disks_storage_class_name: str | None
    jobs_namespace: str
    jobs_resource_pool_types: Sequence[ResourcePoolType]
    jobs_priority_class_name: str
    jobs_internal_host_template: str
    jobs_fallback_host: str
    idle_jobs: Sequence[IdleJobConfig]
    storages: Sequence[StorageConfig]
    buckets: BucketsConfig
    registry: RegistryConfig
    monitoring: MonitoringConfig
    helm_repo: HelmRepo
    docker_config: DockerConfig
    grafana_username: str | None = None
    grafana_password: str | None = None
    sentry_dsn: URL | None = None
    sentry_sample_rate: float | None = None
    docker_hub_config: DockerConfig | None = None
    aws_region: str = ""
    aws_role_arn: str = ""
    aws_s3_role_arn: str = ""
    gcp_service_account_key: str = ""
    gcp_service_account_key_base64: str = ""
    services_priority_class_name: str = ""

    def get_storage_claim_name(self, path: str) -> str:
        name = f"{self.release_name}-storage"
        if path:
            name += path.replace("/", "-")
        return name

    @property
    def image_registry(self) -> str:
        registry = self.docker_config.url.host
        assert registry
        return registry

    def get_image(self, name: str) -> str:
        url = str(self.docker_config.url / name)
        return url.replace("http://", "").replace("https://", "")

    def get_image_repo(self, name: str) -> str:
        url = self.docker_config.url / name
        return url.path.lstrip("/")

    def create_dns_config(
        self,
        ingress_service: dict[str, Any] | None = None,
        aws_ingress_lb: dict[str, Any] | None = None,
    ) -> DNSConfig | None:
        if not ingress_service and not self.ingress_public_ips:
            return None
        a_records: list[ARecord] = []
        if self.ingress_public_ips:
            ips = [str(ip) for ip in self.ingress_public_ips]
            a_records.extend(
                (
                    ARecord(name=f"{self.ingress_dns_name}.", ips=ips),
                    ARecord(name=f"*.jobs.{self.ingress_dns_name}.", ips=ips),
                    ARecord(name=f"*.apps.{self.ingress_dns_name}.", ips=ips),
                    ARecord(name=f"registry.{self.ingress_dns_name}.", ips=ips),
                    ARecord(name=f"metrics.{self.ingress_dns_name}.", ips=ips),
                )
            )
            if self.buckets.provider == BucketsProvider.MINIO:
                a_records.append(
                    ARecord(name=f"blob.{self.ingress_dns_name}.", ips=ips)
                )
        elif aws_ingress_lb and ingress_service:
            ingress_host = ingress_service["status"]["loadBalancer"]["ingress"][0][
                "hostname"
            ]
            ingress_zone_id = aws_ingress_lb["CanonicalHostedZoneId"]
            a_records.extend(
                (
                    ARecord(
                        name=f"{self.ingress_dns_name}.",
                        dns_name=ingress_host,
                        zone_id=ingress_zone_id,
                    ),
                    ARecord(
                        name=f"*.jobs.{self.ingress_dns_name}.",
                        dns_name=ingress_host,
                        zone_id=ingress_zone_id,
                    ),
                    ARecord(
                        name=f"*.apps.{self.ingress_dns_name}.",
                        dns_name=ingress_host,
                        zone_id=ingress_zone_id,
                    ),
                    ARecord(
                        name=f"registry.{self.ingress_dns_name}.",
                        dns_name=ingress_host,
                        zone_id=ingress_zone_id,
                    ),
                    ARecord(
                        name=f"metrics.{self.ingress_dns_name}.",
                        dns_name=ingress_host,
                        zone_id=ingress_zone_id,
                    ),
                )
            )
        elif ingress_service and ingress_service["spec"]["type"] == "LoadBalancer":
            ingress_host = ingress_service["status"]["loadBalancer"]["ingress"][0]["ip"]
            a_records.extend(
                (
                    ARecord(
                        name=f"{self.ingress_dns_name}.",
                        ips=[ingress_host],
                    ),
                    ARecord(
                        name=f"*.jobs.{self.ingress_dns_name}.",
                        ips=[ingress_host],
                    ),
                    ARecord(
                        name=f"*.apps.{self.ingress_dns_name}.",
                        ips=[ingress_host],
                    ),
                    ARecord(
                        name=f"registry.{self.ingress_dns_name}.",
                        ips=[ingress_host],
                    ),
                    ARecord(
                        name=f"metrics.{self.ingress_dns_name}.",
                        ips=[ingress_host],
                    ),
                )
            )
            if self.buckets.provider == BucketsProvider.MINIO:
                a_records.append(
                    ARecord(name=f"blob.{self.ingress_dns_name}.", ips=[ingress_host])
                )
        else:
            return None
        return DNSConfig(name=self.ingress_dns_name, a_records=a_records)

    def create_orchestrator_config(self, cluster: Cluster) -> OrchestratorConfig | None:
        assert cluster.orchestrator
        orchestrator = replace(
            cluster.orchestrator,
            job_internal_hostname_template=self.jobs_internal_host_template,
        )
        if self.kubernetes_tpu_network:
            orchestrator = replace(
                orchestrator,
                resource_pool_types=self._update_tpu_network(
                    orchestrator.resource_pool_types,
                    self.kubernetes_tpu_network,
                ),
            )
        if cluster.orchestrator == orchestrator:
            return None
        return orchestrator

    @classmethod
    def _update_tpu_network(
        cls,
        resource_pools_types: Sequence[ResourcePoolType],
        tpu_network: IPv4Network,
    ) -> Sequence[ResourcePoolType]:
        result = []
        for rpt in resource_pools_types:
            if rpt.tpu:
                result.append(
                    replace(rpt, tpu=replace(rpt.tpu, ipv4_cidr_block=str(tpu_network)))
                )
            else:
                result.append(rpt)
        return result


class PlatformConfigFactory:
    def __init__(self, config: Config) -> None:
        self._config = config

    def create(self, platform_body: kopf.Body, cluster: Cluster) -> PlatformConfig:
        assert cluster.credentials
        assert cluster.orchestrator
        assert cluster.disks
        assert cluster.dns
        assert cluster.ingress
        metadata = Metadata(platform_body["metadata"])
        spec = Spec(platform_body["spec"])
        release_name = self._config.helm_release_names.platform
        docker_config = self._create_neuro_docker_config(
            cluster,
            (
                spec.kubernetes.docker_config_secret_name
                or f"{release_name}-docker-config"
            ),
            spec.kubernetes.docker_config_secret_create,
        )
        docker_hub_config = self._create_docker_hub_config(
            cluster, f"{release_name}-docker-hub-config"
        )
        jobs_namespace = self._config.platform_namespace + "-jobs"
        service_account_annotations: dict[str, str] = {}
        if spec.iam.aws_role_arn:
            service_account_annotations["eks.amazonaws.com/role-arn"] = (
                spec.iam.aws_role_arn
            )
        return PlatformConfig(
            release_name=release_name,
            auth_url=self._config.platform_auth_url,
            ingress_auth_url=self._config.platform_ingress_auth_url,
            config_url=self._config.platform_config_url,
            admin_url=self._config.platform_admin_url,
            api_url=self._config.platform_api_url,
            notifications_url=self._config.platform_notifications_url,
            token=spec.token,
            cluster_name=metadata.name,
            namespace=self._config.platform_namespace,
            service_account_name="default",
            service_account_annotations=service_account_annotations,
            image_pull_secret_names=self._create_image_pull_secret_names(
                docker_config, docker_hub_config
            ),
            pre_pull_images=cluster.orchestrator.pre_pull_images,
            standard_storage_class_name=(
                spec.kubernetes.standard_storage_class_name or None
            ),
            kubernetes_provider=spec.kubernetes.provider,
            kubernetes_version=self._config.kube_config.version,
            kubernetes_tpu_network=spec.kubernetes.tpu_network,
            kubelet_port=int(spec.kubernetes.kubelet_port or 10250),
            nvidia_dcgm_port=9400,
            node_labels=LabelsConfig(
                job=spec.kubernetes.node_label_job or LabelsConfig.job,
                node_pool=(
                    spec.kubernetes.node_label_node_pool or LabelsConfig.node_pool
                ),
                accelerator=(
                    spec.kubernetes.node_label_accelerator or LabelsConfig.accelerator
                ),
                preemptible=(
                    spec.kubernetes.node_label_preemptible or LabelsConfig.preemptible
                ),
            ),
            ingress_dns_name=cluster.dns.name,
            ingress_url=URL(f"https://{cluster.dns.name}"),
            ingress_registry_url=URL(f"https://registry.{cluster.dns.name}"),
            ingress_metrics_url=URL(f"https://metrics.{cluster.dns.name}"),
            ingress_acme_enabled=(
                not spec.ingress_controller.ssl_cert_data
                or not spec.ingress_controller.ssl_cert_key_data
            ),
            ingress_acme_environment=cluster.ingress.acme_environment,
            ingress_controller_install=spec.ingress_controller.enabled,
            ingress_controller_replicas=spec.ingress_controller.replicas or 2,
            ingress_public_ips=spec.ingress_controller.public_ips,
            ingress_cors_origins=cluster.ingress.cors_origins,
            ingress_service_type=IngressServiceType(
                spec.ingress_controller.service_type or IngressServiceType.LOAD_BALANCER
            ),
            ingress_service_name="traefik",
            ingress_service_annotations=spec.ingress_controller.service_annotations,
            ingress_load_balancer_source_ranges=(
                spec.ingress_controller.load_balancer_source_ranges
            ),
            ingress_node_port_http=spec.ingress_controller.node_port_http,
            ingress_node_port_https=spec.ingress_controller.node_port_https,
            ingress_host_port_http=spec.ingress_controller.host_port_http,
            ingress_host_port_https=spec.ingress_controller.host_port_https,
            ingress_ssl_cert_data=spec.ingress_controller.ssl_cert_data,
            ingress_ssl_cert_key_data=spec.ingress_controller.ssl_cert_key_data,
            jobs_namespace=jobs_namespace,
            jobs_resource_pool_types=cluster.orchestrator.resource_pool_types,
            jobs_priority_class_name=f"{self._config.helm_release_names.platform}-job",
            jobs_internal_host_template=f"{{job_id}}.{jobs_namespace}",
            jobs_fallback_host=cluster.orchestrator.job_fallback_hostname,
            idle_jobs=cluster.orchestrator.idle_jobs,
            storages=[self._create_storage(s) for s in spec.storages],
            buckets=self._create_buckets(spec.blob_storage, cluster),
            registry=self._create_registry(spec.registry),
            monitoring=self._create_monitoring(spec.monitoring),
            disks_storage_limit_per_user=cluster.disks.storage_limit_per_user,
            disks_storage_class_name=spec.disks.storage_class_name or None,
            helm_repo=self._create_helm_repo(cluster),
            docker_config=docker_config,
            docker_hub_config=docker_hub_config,
            grafana_username=(
                cluster.credentials.grafana.username
                if cluster.credentials.grafana
                else None
            ),
            grafana_password=(
                cluster.credentials.grafana.password
                if cluster.credentials.grafana
                else None
            ),
            sentry_dsn=(
                cluster.credentials.sentry.public_dsn
                if cluster.credentials.sentry
                else None
            ),
            sentry_sample_rate=(
                cluster.credentials.sentry.sample_rate
                if cluster.credentials.sentry
                else None
            ),
            aws_region=spec.iam.aws_region,
            aws_role_arn=spec.iam.aws_role_arn,
            aws_s3_role_arn=spec.iam.aws_s3_role_arn,
            gcp_service_account_key=self._base64_decode(
                spec.iam.gcp_service_account_key_base64
            ),
            gcp_service_account_key_base64=spec.iam.gcp_service_account_key_base64,
            services_priority_class_name=f"{self._config.platform_namespace}-services",
        )

    def _create_helm_repo(self, cluster: Cluster) -> HelmRepo:
        assert cluster.credentials
        assert cluster.credentials.neuro_helm
        return HelmRepo(
            url=cluster.credentials.neuro_helm.url,
            username=cluster.credentials.neuro_helm.username or "",
            password=cluster.credentials.neuro_helm.password or "",
        )

    def _create_neuro_docker_config(
        self, cluster: Cluster, secret_name: str, create_secret: bool
    ) -> DockerConfig:
        assert cluster.credentials
        assert cluster.credentials.neuro_registry
        return self._create_docker_config(
            cluster.credentials.neuro_registry, secret_name, create_secret
        )

    def _create_docker_hub_config(
        self, cluster: Cluster, secret_name: str
    ) -> DockerConfig | None:
        assert cluster.credentials
        if cluster.credentials.docker_hub is None:
            return None
        return self._create_docker_config(
            cluster.credentials.docker_hub, secret_name, True
        )

    def _create_docker_config(
        self, registry: DockerRegistryConfig, secret_name: str, create_secret: bool
    ) -> DockerConfig:
        if not registry.username or not registry.password:
            secret_name = ""
            create_secret = False
        return DockerConfig(
            url=registry.url,
            email=registry.email or "",
            username=registry.username or "",
            password=registry.password or "",
            secret_name=secret_name,
            create_secret=create_secret,
        )

    def _create_image_pull_secret_names(
        self, *docker_config: DockerConfig | None
    ) -> Sequence[str]:
        result: list[str] = []
        for config in docker_config:
            if config and config.secret_name:
                result.append(config.secret_name)
        return result

    def _create_storage(self, spec: StorageSpec) -> StorageConfig:
        if not spec:
            raise ValueError("Storage spec is empty")

        if StorageType.KUBERNETES in spec:
            return StorageConfig(
                type=StorageType.KUBERNETES,
                path=spec.path,
                storage_class_name=spec.storage_class_name,
                storage_size=spec.storage_size,
            )
        elif StorageType.NFS in spec:
            return StorageConfig(
                type=StorageType.NFS,
                path=spec.path,
                nfs_server=spec.nfs_server,
                nfs_export_path=spec.nfs_export_path,
            )
        elif StorageType.SMB in spec:
            return StorageConfig(
                type=StorageType.SMB,
                path=spec.path,
                smb_server=spec.smb_server,
                smb_share_name=spec.smb_share_name,
                smb_username=spec.smb_username,
                smb_password=spec.smb_password,
            )
        elif StorageType.AZURE_fILE in spec:
            return StorageConfig(
                type=StorageType.AZURE_fILE,
                path=spec.path,
                azure_storage_account_name=spec.azure_storage_account_name,
                azure_storage_account_key=spec.azure_storage_account_key,
                azure_share_name=spec.azure_share_name,
            )
        elif StorageType.GCS in spec:
            return StorageConfig(
                type=StorageType.GCS, gcs_bucket_name=spec.gcs_bucket_name
            )
        else:
            raise ValueError("Storage type is not supported")

    def _create_buckets(self, spec: BlobStorageSpec, cluster: Cluster) -> BucketsConfig:
        if not spec:
            raise ValueError("Blob storage spec is empty")

        assert cluster.credentials
        assert cluster.buckets
        assert cluster.dns

        if BucketsProvider.AWS in spec:
            return BucketsConfig(
                provider=BucketsProvider.AWS,
                disable_creation=cluster.buckets.disable_creation,
                aws_region=spec.aws_region,
            )
        elif BucketsProvider.GCP in spec:
            return BucketsConfig(
                provider=BucketsProvider.GCP,
                gcp_project=spec.gcp_project,
                disable_creation=cluster.buckets.disable_creation,
            )
        elif BucketsProvider.AZURE in spec:
            return BucketsConfig(
                provider=BucketsProvider.AZURE,
                disable_creation=cluster.buckets.disable_creation,
                azure_storage_account_name=spec.azure_storrage_account_name,
                azure_storage_account_key=spec.azure_storrage_account_key,
            )
        elif BucketsProvider.EMC_ECS in spec:
            return BucketsConfig(
                provider=BucketsProvider.EMC_ECS,
                disable_creation=cluster.buckets.disable_creation,
                emc_ecs_access_key_id=spec.emc_ecs_access_key_id,
                emc_ecs_secret_access_key=spec.emc_ecs_secret_access_key,
                emc_ecs_s3_assumable_role=spec.emc_ecs_s3_role,
                emc_ecs_s3_endpoint=URL(spec.emc_ecs_s3_endpoint),
                emc_ecs_management_endpoint=URL(spec.emc_ecs_management_endpoint),
            )
        elif BucketsProvider.OPEN_STACK in spec:
            return BucketsConfig(
                provider=BucketsProvider.OPEN_STACK,
                disable_creation=cluster.buckets.disable_creation,
                open_stack_region_name=spec.open_stack_region,
                open_stack_username=spec.open_stack_username,
                open_stack_password=spec.open_stack_password,
                open_stack_endpoint=URL(spec.open_stack_endpoint),
                open_stack_s3_endpoint=URL(spec.open_stack_s3_endpoint),
            )
        elif BucketsProvider.MINIO in spec:
            return BucketsConfig(
                provider=BucketsProvider.MINIO,
                disable_creation=cluster.buckets.disable_creation,
                minio_url=URL(spec.minio_url),
                # Ingress should be configured manually in this case
                minio_public_url=URL(f"https://blob.{cluster.dns.name}"),
                minio_region=spec.minio_region,
                minio_access_key=spec.minio_access_key,
                minio_secret_key=spec.minio_secret_key,
            )
        elif "kubernetes" in spec:
            assert cluster.credentials.minio
            return BucketsConfig(
                provider=BucketsProvider.MINIO,
                disable_creation=cluster.buckets.disable_creation,
                minio_install=True,
                minio_url=URL.build(
                    scheme="http",
                    host=f"{self._config.helm_release_names.platform}-minio",
                    port=9000,
                ),
                # Ingress should be configured manually in this case
                minio_public_url=URL(f"https://blob.{cluster.dns.name}"),
                minio_region="minio",
                minio_access_key=cluster.credentials.minio.username,
                minio_secret_key=cluster.credentials.minio.password,
                minio_storage_class_name=spec.kubernetes_storage_class_name,
                minio_storage_size=spec.kubernetes_storage_size or "10Gi",
            )
        else:
            raise ValueError("Bucket provider is not supported")

    def _create_registry(self, spec: RegistrySpec) -> RegistryConfig:
        if not spec:
            raise ValueError("Registry spec is empty")

        if RegistryProvider.AWS in spec:
            return RegistryConfig(
                provider=RegistryProvider.AWS,
                aws_account_id=spec.aws_account_id,
                aws_region=spec.aws_region,
            )
        elif RegistryProvider.GCP in spec:
            return RegistryConfig(
                provider=RegistryProvider.GCP,
                gcp_project=spec.gcp_project,
            )
        elif RegistryProvider.AZURE in spec:
            url = URL(spec.azure_url)
            if not url.scheme:
                url = URL(f"https://{url!s}")
            return RegistryConfig(
                provider=RegistryProvider.AZURE,
                azure_url=url,
                azure_username=spec.azure_username,
                azure_password=spec.azure_password,
            )
        elif RegistryProvider.DOCKER in spec:
            return RegistryConfig(
                provider=RegistryProvider.DOCKER,
                docker_registry_url=URL(spec.docker_url),
                docker_registry_username=spec.docker_username,
                docker_registry_password=spec.docker_password,
            )
        elif "kubernetes" in spec:
            return RegistryConfig(
                provider=RegistryProvider.DOCKER,
                docker_registry_install=True,
                docker_registry_url=URL.build(
                    scheme="http",
                    host=f"{self._config.helm_release_names.platform}-docker-registry",
                    port=5000,
                ),
                docker_registry_storage_class_name=spec.kubernetes_storage_class_name,
                docker_registry_storage_size=spec.kubernetes_storage_size or "10Gi",
            )
        else:
            raise ValueError("Registry provider is not supported")

    def _create_monitoring(self, spec: MonitoringSpec) -> MonitoringConfig:
        if not spec:
            raise ValueError("Monitoring spec is empty")

        metrics_enabled = not self._config.is_standalone

        if not metrics_enabled:
            return MonitoringConfig(
                logs_region=spec.logs_region,
                logs_bucket_name=spec.logs_bucket,
                metrics_enabled=False,
            )
        elif "blobStorage" in spec.metrics:
            return MonitoringConfig(
                logs_region=spec.logs_region,
                logs_bucket_name=spec.logs_bucket,
                metrics_enabled=True,
                metrics_storage_type=MetricsStorageType.BUCKETS,
                metrics_region=spec.metrics_region,
                metrics_bucket_name=spec.metrics_bucket,
                metrics_retention_time=(
                    spec.metrics_retention_time
                    or MonitoringConfig.metrics_retention_time
                ),
            )
        elif "kubernetes" in spec.metrics:
            return MonitoringConfig(
                logs_bucket_name=spec.logs_bucket,
                metrics_enabled=True,
                metrics_storage_type=MetricsStorageType.KUBERNETES,
                metrics_storage_class_name=spec.metrics_storage_class_name,
                metrics_storage_size=spec.metrics_storage_size or "10Gi",
                metrics_retention_time=(
                    spec.metrics_retention_time
                    or MonitoringConfig.metrics_retention_time
                ),
                metrics_region=spec.metrics_region,
            )
        else:
            raise ValueError("Metrics storage type is not supported")

    @classmethod
    def _base64_decode(cls, value: str | None) -> str:
        if not value:
            return ""
        return b64decode(value.encode("utf-8")).decode("utf-8")
