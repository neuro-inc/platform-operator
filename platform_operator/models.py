from __future__ import annotations

import json
import os
from base64 import b64decode, urlsafe_b64decode
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path
from typing import Any, NoReturn

import kopf
from neuro_config_client import (
    ACMEEnvironment,
    Cluster,
    DockerRegistryConfig,
    IdleJobConfig,
    ResourcePoolType,
)
from pydantic import BaseModel, ConfigDict, Field, RootModel
from pydantic.alias_generators import to_camel
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
    url: URL
    auth_type: KubeClientAuthType = KubeClientAuthType.NONE
    cert_authority_path: Path | None = None
    auth_cert_path: Path | None = None
    auth_cert_key_path: Path | None = None
    auth_token_path: Path | None = None
    conn_timeout_s: int = 300
    read_timeout_s: int = 100
    conn_pool_size: int = 100

    @classmethod
    def load_from_env(cls, env: Mapping[str, str] | None = None) -> KubeConfig:
        env = env or os.environ
        return cls(
            url=URL(env["NP_KUBE_URL"]),
            auth_type=KubeClientAuthType(env["NP_KUBE_AUTH_TYPE"]),
            cert_authority_path=cls._convert_to_path(
                env.get("NP_KUBE_CERT_AUTHORITY_PATH")
            ),
            auth_cert_path=cls._convert_to_path(env.get("NP_KUBE_AUTH_CERT_PATH")),
            auth_cert_key_path=cls._convert_to_path(
                env.get("NP_KUBE_AUTH_CERT_KEY_PATH")
            ),
            auth_token_path=cls._convert_to_path(env.get("NP_KUBE_AUTH_TOKEN_PATH")),
        )

    def read_auth_token_from_path(self) -> str | NoReturn:
        if not self.auth_token_path:
            raise ValueError("auth_token_path must be set")
        return Path(self.auth_token_path).read_text()

    @property
    def auth_token_exp_ts(self) -> int | NoReturn:
        payload = self.read_auth_token_from_path().split(".")[1]
        decoded_payload = json.loads(
            urlsafe_b64decode(payload + "=" * (4 - len(payload) % 4))
        )
        return decoded_payload["exp"]

    @staticmethod
    def _convert_to_path(value: str | None) -> Path | None:
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


class HelmChartNames:
    docker_registry: str = "docker-registry"
    harbor: str = "harbor"
    minio: str = "minio"
    minio_gateway: str = "minio-gateway"
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
    platform_metadata: str = "platform-metadata"
    pgo: str = "apps-postgres-operator"
    keda: str = "keda"
    alloy: str = "alloy"
    loki: str = "loki"
    spark_operator: str = "spark-operator"
    external_secrets: str = "external-secrets"


@dataclass(frozen=True)
class HelmChartVersions:
    platform: str


@dataclass(frozen=True)
class Config:
    log_level: str
    retries: int
    backoff: int
    kube_config: KubeConfig
    helm_release_names: HelmReleaseNames
    helm_chart_versions: HelmChartVersions
    vault_url: URL
    platform_auth_url: URL
    platform_ingress_auth_url: URL
    platform_config_url: URL
    platform_admin_url: URL
    platform_config_watch_interval_s: float
    platform_api_url: URL
    platform_apps_url: URL
    platform_notifications_url: URL
    platform_events_url: URL
    platform_namespace: str
    platform_lock_secret_name: str
    acme_ca_staging_path: str
    is_standalone: bool

    @classmethod
    def load_from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        env = env or os.environ
        return cls(
            log_level=(env.get("NP_CONTROLLER_LOG_LEVEL") or "INFO").upper(),
            retries=int(env.get("NP_CONTROLLER_RETRIES") or "3"),
            backoff=int(env.get("NP_CONTROLLER_BACKOFF") or "60"),
            kube_config=KubeConfig.load_from_env(env),
            helm_release_names=HelmReleaseNames(platform="platform"),
            helm_chart_versions=HelmChartVersions(
                platform=env["NP_HELM_PLATFORM_CHART_VERSION"],
            ),
            vault_url=URL(env["NP_VAULT_URL"]),
            platform_auth_url=URL(env["NP_PLATFORM_AUTH_URL"]),
            platform_ingress_auth_url=URL(env["NP_PLATFORM_INGRESS_AUTH_URL"]),
            platform_config_url=URL(env["NP_PLATFORM_CONFIG_URL"]),
            platform_admin_url=URL(env["NP_PLATFORM_ADMIN_URL"]),
            platform_config_watch_interval_s=float(
                env.get("NP_PLATFORM_CONFIG_WATCH_INTERVAL_S", "15")
            ),
            platform_api_url=URL(env["NP_PLATFORM_API_URL"]),
            platform_apps_url=URL(env["NP_PLATFORM_APPS_URL"]),
            platform_notifications_url=URL(env["NP_PLATFORM_NOTIFICATIONS_URL"]),
            platform_events_url=URL(env["NP_PLATFORM_EVENTS_URL"]),
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

    @property
    def blob_storage_bucket(self) -> str:
        return self["blobStorage"].get("bucket", "")


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
    def metrics_bucket(self) -> str:
        return self["metrics"]["blobStorage"].get("bucket", "")

    @property
    def metrics_node_exporter_enabled(self) -> bool:
        return self["metrics"].get("nodeExporter", {}).get("enabled", True)

    @property
    def loki_enabled(self) -> bool:
        return self["logs"].get("loki", {}).get("enabled", True)

    @property
    def loki_dns_service(self) -> str | None:
        return self["logs"].get("loki", {}).get("dnsService")

    @property
    def loki_endpoint(self) -> str | None:
        return self["logs"].get("loki", {}).get("endpoint")

    @property
    def alloy_enabled(self) -> bool:
        return self["logs"].get("alloy", {}).get("enabled", True)


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


class RegistryProvider(str, Enum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    DOCKER = "docker"


class DockerRegistryStorageDriver(str, Enum):
    FILE_SYSTEM = "file_system"
    S3 = "s3"


class DockerRegistryType(str, Enum):
    DOCKER = "docker"
    HARBOR = "harbor"


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
    docker_registry_type: DockerRegistryType = DockerRegistryType.DOCKER
    docker_registry_url: URL | None = None
    docker_registry_username: str = ""
    docker_registry_password: str = ""

    docker_registry_storage_driver: DockerRegistryStorageDriver = (
        DockerRegistryStorageDriver.FILE_SYSTEM
    )

    docker_registry_file_system_storage_class_name: str = ""
    docker_registry_file_system_storage_size: str = ""

    docker_registry_s3_endpoint: URL | None = None
    docker_registry_s3_region: str = ""
    docker_registry_s3_bucket: str = ""
    docker_registry_s3_access_key: str = ""
    docker_registry_s3_secret_key: str = ""
    docker_registry_s3_disable_redirect: bool = False
    docker_registry_s3_force_path_style: bool = False


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
    azure_minio_gateway_region: str = "minio"

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
    emc_ecs_region: str = "emc-ecs"

    open_stack_username: str = ""
    open_stack_password: str = ""
    open_stack_endpoint: URL | None = None
    open_stack_s3_endpoint: URL | None = None
    open_stack_region_name: str = ""


@dataclass(frozen=True)
class AppsOperatorsConfig:
    postgres_operator_enabled: bool = True
    spark_operator_enabled: bool = True
    keda_enabled: bool = True


@dataclass(frozen=True)
class MinioGatewayConfig:
    root_user: str
    root_user_password: str
    endpoint_url: str = "http://minio-gateway:9000"


@dataclass(frozen=True)
class MonitoringConfig:
    logs_bucket_name: str
    logs_region: str = ""
    metrics_enabled: bool = True
    metrics_bucket_name: str = ""
    metrics_region: str = ""
    metrics_node_exporter_enabled: bool = True
    loki_enabled: bool = True
    loki_dns_service: str = "kube-dns"
    loki_endpoint: str = ""
    alloy_enabled: bool = True


@dataclass(frozen=True)
class PrometheusConfig:
    @dataclass(frozen=True)
    class Federation:
        @dataclass(frozen=True)
        class Auth:
            username: str
            password: str = field(repr=False)

        auth: Auth

    federation: Federation


class ClusterSecretStoreSpec(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
    )

    class Vault(BaseModel):
        model_config = ConfigDict(
            alias_generator=to_camel,
            validate_by_name=True,
            validate_by_alias=True,
        )

        server: str = ""
        path: str = ""
        version: str = "v2"
        auth: dict[str, Any] = Field(default_factory=dict)

    vault: Vault = Field(default_factory=Vault)


class ExternalSecretsSpec(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
    )

    class HelmValues(BaseModel):
        model_config = ConfigDict(
            alias_generator=to_camel,
            validate_by_name=True,
            validate_by_alias=True,
            extra="allow",
        )

    enabled: bool = True
    helm_values: HelmValues = Field(default_factory=HelmValues)


class ExternalSecretObjectsSpec(
    RootModel[Sequence["ExternalSecretObjectsSpec.ExternalSecretObject"]]
):
    class ExternalSecretObject(BaseModel):
        class RemoteRef(BaseModel):
            key: str
            property: str

        name: str
        data: dict[str, RemoteRef]

    root: Sequence[ExternalSecretObject] = Field(default_factory=list)


class PlatformStorageSpec(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
    )

    class HelmValues(BaseModel):
        model_config = ConfigDict(
            alias_generator=to_camel,
            validate_by_name=True,
            validate_by_alias=True,
            extra="allow",
        )

        class Storage(BaseModel):
            model_config = ConfigDict(extra="allow")

            path: str | None = None

        storages: Sequence[Storage] = Field(min_length=1)

    helm_values: HelmValues


class PlatformSpec(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        extra="allow",
    )

    external_secrets: ExternalSecretsSpec = ExternalSecretsSpec()
    cluster_secret_store: ClusterSecretStoreSpec = Field(
        default_factory=ClusterSecretStoreSpec
    )
    external_secret_objects: ExternalSecretObjectsSpec = Field(
        default_factory=ExternalSecretObjectsSpec
    )
    platform_storage: PlatformStorageSpec


@dataclass(frozen=True)
class PlatformConfig:
    release_name: str
    auth_url: URL
    ingress_auth_url: URL
    config_url: URL
    admin_url: URL
    api_url: URL
    apps_url: URL
    notifications_url: URL
    events_url: URL
    token: str
    cluster_name: str
    service_account_name: str
    service_account_annotations: dict[str, str]
    image_pull_secret_names: Sequence[str]
    pre_pull_images: Sequence[str]
    standard_storage_class_name: str | None
    kubernetes_tpu_network: IPv4Network | None
    node_labels: LabelsConfig
    kubelet_port: int
    nvidia_dcgm_port: int
    namespace: str
    ingress_dns_name: str
    ingress_url: URL
    ingress_registry_url: URL
    ingress_metrics_url: URL
    ingress_grafana_url: URL
    ingress_prometheus_url: URL
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
    buckets: BucketsConfig
    registry: RegistryConfig
    monitoring: MonitoringConfig
    helm_repo: HelmRepo
    docker_config: DockerConfig
    prometheus: PrometheusConfig
    platform_spec: PlatformSpec
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
    minio_gateway: MinioGatewayConfig | None = None
    apps_operator_config: AppsOperatorsConfig = field(
        default_factory=AppsOperatorsConfig
    )

    def get_storage_claim_name(self, path: str | None) -> str:
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


class PlatformConfigFactory:
    def __init__(self, config: Config) -> None:
        self._config = config

    def create(self, platform_body: kopf.Body, cluster: Cluster) -> PlatformConfig:
        assert cluster.credentials
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
        buckets_config = self._create_buckets(spec.blob_storage, cluster)
        platform_spec = PlatformSpec.model_validate(
            {
                "externalSecrets": ExternalSecretsSpec.model_validate(
                    platform_body["spec"].get("externalSecrets", {})
                ),
                "clusterSecretStore": self._create_cluster_secret_store_spec(
                    platform_body
                ),
                "externalSecretObjects": ExternalSecretObjectsSpec.model_validate(
                    platform_body["spec"].get("externalSecretObjects") or []
                ),
                "platformStorage": PlatformStorageSpec.model_validate(
                    platform_body["spec"]["platformStorage"]
                ),
            }
        )
        return PlatformConfig(
            release_name=release_name,
            auth_url=self._config.platform_auth_url,
            ingress_auth_url=self._config.platform_ingress_auth_url,
            config_url=self._config.platform_config_url,
            admin_url=self._config.platform_admin_url,
            api_url=self._config.platform_api_url,
            apps_url=self._config.platform_apps_url,
            notifications_url=self._config.platform_notifications_url,
            events_url=self._config.platform_events_url,
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
            ingress_grafana_url=URL(f"https://grafana.{cluster.dns.name}"),
            ingress_metrics_url=URL(f"https://metrics.{cluster.dns.name}"),
            ingress_prometheus_url=URL(f"https://prometheus.{cluster.dns.name}"),
            ingress_acme_enabled=(
                not spec.ingress_controller.ssl_cert_data
                or not spec.ingress_controller.ssl_cert_key_data
            ),
            ingress_acme_environment=cluster.ingress.acme_environment,
            ingress_controller_install=spec.ingress_controller.enabled,
            ingress_controller_replicas=spec.ingress_controller.replicas or 2,
            ingress_public_ips=spec.ingress_controller.public_ips,
            ingress_cors_origins=sorted(
                {
                    *cluster.ingress.default_cors_origins,
                    *cluster.ingress.additional_cors_origins,
                }
            ),
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
            buckets=buckets_config,
            registry=self._create_registry(
                spec.registry, buckets_config=buckets_config, cluster=cluster
            ),
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
            minio_gateway=self._create_minio_gateway(spec),
            prometheus=self._create_prometheus(cluster),
            platform_spec=platform_spec,
        )

    def _create_cluster_secret_store_spec(
        self, platform_body: kopf.Body
    ) -> ClusterSecretStoreSpec:
        cluster_name = platform_body["metadata"]["name"]
        spec = ClusterSecretStoreSpec.model_validate(
            platform_body["spec"].get("clusterSecretStore", {})
        )
        spec.vault.server = spec.vault.server or str(self._config.vault_url)
        spec.vault.path = spec.vault.path or f"{cluster_name}--kv-v2"
        spec.vault.version = spec.vault.version or "v2"
        spec.vault.auth = spec.vault.auth or {
            "kubernetes": {
                "mountPath": f"{cluster_name}--jwt",
                "role": f"{cluster_name}--platform",
            }
        }
        return spec

    def _create_helm_repo(self, cluster: Cluster) -> HelmRepo:
        assert cluster.credentials
        return HelmRepo(
            url=cluster.credentials.neuro_helm.url,
            username=cluster.credentials.neuro_helm.username or "",
            password=cluster.credentials.neuro_helm.password or "",
        )

    def _create_neuro_docker_config(
        self, cluster: Cluster, secret_name: str, create_secret: bool
    ) -> DockerConfig:
        assert cluster.credentials
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

    def _create_buckets(self, spec: BlobStorageSpec, cluster: Cluster) -> BucketsConfig:
        if not spec:
            raise ValueError("Blob storage spec is empty")

        assert cluster.credentials

        if BucketsProvider.AWS in spec:
            return BucketsConfig(
                provider=BucketsProvider.AWS,
                disable_creation=cluster.buckets.disable_creation,
                aws_region=spec.aws_region,
            )
        if BucketsProvider.GCP in spec:
            return BucketsConfig(
                provider=BucketsProvider.GCP,
                gcp_project=spec.gcp_project,
                disable_creation=cluster.buckets.disable_creation,
            )
        if BucketsProvider.AZURE in spec:
            return BucketsConfig(
                provider=BucketsProvider.AZURE,
                disable_creation=cluster.buckets.disable_creation,
                azure_storage_account_name=spec.azure_storrage_account_name,
                azure_storage_account_key=spec.azure_storrage_account_key,
            )
        if BucketsProvider.EMC_ECS in spec:
            return BucketsConfig(
                provider=BucketsProvider.EMC_ECS,
                disable_creation=cluster.buckets.disable_creation,
                emc_ecs_access_key_id=spec.emc_ecs_access_key_id,
                emc_ecs_secret_access_key=spec.emc_ecs_secret_access_key,
                emc_ecs_s3_assumable_role=spec.emc_ecs_s3_role,
                emc_ecs_s3_endpoint=URL(spec.emc_ecs_s3_endpoint),
                emc_ecs_management_endpoint=URL(spec.emc_ecs_management_endpoint),
            )
        if BucketsProvider.OPEN_STACK in spec:
            return BucketsConfig(
                provider=BucketsProvider.OPEN_STACK,
                disable_creation=cluster.buckets.disable_creation,
                open_stack_region_name=spec.open_stack_region,
                open_stack_username=spec.open_stack_username,
                open_stack_password=spec.open_stack_password,
                open_stack_endpoint=URL(spec.open_stack_endpoint),
                open_stack_s3_endpoint=URL(spec.open_stack_s3_endpoint),
            )
        if BucketsProvider.MINIO in spec:
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
        if "kubernetes" in spec:
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
        raise ValueError("Bucket provider is not supported")

    def _create_registry(
        self, spec: RegistrySpec, *, buckets_config: BucketsConfig, cluster: Cluster
    ) -> RegistryConfig:
        if not spec:
            raise ValueError("Registry spec is empty")

        if RegistryProvider.AWS in spec:
            return RegistryConfig(
                provider=RegistryProvider.AWS,
                aws_account_id=spec.aws_account_id,
                aws_region=spec.aws_region,
            )
        if RegistryProvider.GCP in spec:
            return RegistryConfig(
                provider=RegistryProvider.GCP,
                gcp_project=spec.gcp_project,
            )
        if RegistryProvider.AZURE in spec:
            url = URL(spec.azure_url)
            if not url.scheme:
                url = URL(f"https://{url!s}")
            return RegistryConfig(
                provider=RegistryProvider.AZURE,
                azure_url=url,
                azure_username=spec.azure_username,
                azure_password=spec.azure_password,
            )
        if RegistryProvider.DOCKER in spec:
            return RegistryConfig(
                provider=RegistryProvider.DOCKER,
                docker_registry_url=URL(spec.docker_url),
                docker_registry_username=spec.docker_username,
                docker_registry_password=spec.docker_password,
            )
        if "kubernetes" in spec:
            reg_type = DockerRegistryType(
                spec.get("kubernetes", {}).get("registry_type", "docker")
            )
            if reg_type == DockerRegistryType.HARBOR:
                docker_registry_url = URL.build(
                    scheme="https", host=f"harbor.apps.{cluster.dns.name}"
                )
            else:
                docker_registry_url = URL.build(
                    scheme="http",
                    host=f"{self._config.helm_release_names.platform}-docker-registry",
                    port=5000,
                )
            return RegistryConfig(
                provider=RegistryProvider.DOCKER,
                docker_registry_install=True,
                docker_registry_type=reg_type,
                docker_registry_url=docker_registry_url,
                docker_registry_storage_driver=DockerRegistryStorageDriver.FILE_SYSTEM,
                docker_registry_file_system_storage_class_name=(
                    spec.kubernetes_storage_class_name
                ),
                docker_registry_file_system_storage_size=spec.kubernetes_storage_size
                or "10Gi",
            )
        if "blobStorage" in spec and buckets_config.provider == BucketsProvider.MINIO:
            return RegistryConfig(
                provider=RegistryProvider.DOCKER,
                docker_registry_install=True,
                docker_registry_url=URL.build(
                    scheme="http",
                    host=f"{self._config.helm_release_names.platform}-docker-registry",
                    port=5000,
                ),
                docker_registry_storage_driver=DockerRegistryStorageDriver.S3,
                docker_registry_s3_endpoint=buckets_config.minio_url,
                docker_registry_s3_region=buckets_config.minio_region,
                docker_registry_s3_bucket=spec.blob_storage_bucket,
                docker_registry_s3_access_key=buckets_config.minio_access_key,
                docker_registry_s3_secret_key=buckets_config.minio_secret_key,
                docker_registry_s3_disable_redirect=True,
                docker_registry_s3_force_path_style=True,
            )
        raise ValueError("Registry provider is not supported")

    def _create_monitoring(self, spec: MonitoringSpec) -> MonitoringConfig:
        if not spec:
            raise ValueError("Monitoring spec is empty")

        metrics_enabled = not self._config.is_standalone
        loki_enabled = spec.loki_enabled
        loki_dns_service = spec.loki_dns_service or MonitoringConfig.loki_dns_service
        loki_endpoint = spec.loki_endpoint or MonitoringConfig.loki_endpoint

        if not loki_enabled and not loki_endpoint:
            raise ValueError("Loki endpoint is required")

        if not metrics_enabled:
            return MonitoringConfig(
                logs_region=spec.logs_region,
                logs_bucket_name=spec.logs_bucket,
                metrics_enabled=False,
                loki_enabled=loki_enabled,
                loki_dns_service=loki_dns_service,
                loki_endpoint=loki_endpoint,
                alloy_enabled=spec.alloy_enabled,
            )
        return MonitoringConfig(
            logs_region=spec.logs_region,
            logs_bucket_name=spec.logs_bucket,
            metrics_enabled=True,
            metrics_region=spec.metrics_region,
            metrics_bucket_name=spec.metrics_bucket,
            metrics_node_exporter_enabled=spec.metrics_node_exporter_enabled,
            loki_enabled=loki_enabled,
            loki_dns_service=loki_dns_service,
            loki_endpoint=loki_endpoint,
            alloy_enabled=spec.alloy_enabled,
        )

    def _create_minio_gateway(self, spec: Spec) -> MinioGatewayConfig | None:
        if BucketsProvider.GCP in spec.blob_storage:
            return MinioGatewayConfig(
                root_user="admin",
                root_user_password=sha256(
                    spec.iam.gcp_service_account_key_base64.encode()
                ).hexdigest(),
            )
        if BucketsProvider.AZURE in spec.blob_storage:
            return MinioGatewayConfig(
                root_user=spec.blob_storage.azure_storrage_account_name,
                root_user_password=spec.blob_storage.azure_storrage_account_key,
            )
        return None

    @classmethod
    def _base64_decode(cls, value: str | None) -> str:
        if not value:
            return ""
        return b64decode(value.encode("utf-8")).decode("utf-8")

    def _create_prometheus(self, cluster: Cluster) -> PrometheusConfig:
        assert cluster.credentials, "cluster credentials required"
        assert cluster.credentials.prometheus, "cluster Prometheus credentials required"
        return PrometheusConfig(
            federation=PrometheusConfig.Federation(
                auth=PrometheusConfig.Federation.Auth(
                    username=cluster.credentials.prometheus.username,
                    password=cluster.credentials.prometheus.password,
                )
            )
        )
