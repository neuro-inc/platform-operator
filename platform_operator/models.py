import copy
import json
import os
from base64 import b64decode, b64encode
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from kopf.structs import bodies
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
    cert_authority_path: Optional[Path] = None
    cert_authority_data_pem: Optional[str] = None
    auth_type: KubeClientAuthType = KubeClientAuthType.NONE
    auth_cert_path: Optional[Path] = None
    auth_cert_key_path: Optional[Path] = None
    auth_token_path: Optional[Path] = None
    auth_token: Optional[str] = None
    conn_timeout_s: int = 300
    read_timeout_s: int = 100
    conn_pool_size: int = 100


@dataclass(frozen=True)
class LabelsConfig:
    job: str = "platform.neuromation.io/job"
    node_pool: str = "platform.neuromation.io/nodepool"
    accelerator: str = "platform.neuromation.io/accelerator"
    preemptible: str = "platform.neuromation.io/preemptible"


class HelmRepoName(str, Enum):
    STABLE = "stable"
    NEURO = "neuro"

    def __repr__(self) -> str:
        return repr(self.value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class HelmRepo:
    name: str
    url: URL
    username: str = ""
    password: str = ""


@dataclass
class HelmReleaseNames:
    platform: str
    obs_csi_driver: str


@dataclass(frozen=True)
class HelmChartNames:
    obs_csi_driver: str = "obs-csi-driver"
    docker_registry: str = "docker-registry"
    minio: str = "minio"
    consul: str = "consul"
    traefik: str = "traefik"
    adjust_inotify: str = "adjust-inotify"
    cluster_autoscaler: str = "cluster-autoscaler"
    nvidia_gpu_driver: str = "nvidia-gpu-driver"
    nvidia_gpu_driver_gcp: str = "nvidia-gpu-driver-gcp"
    platform: str = "platform"
    platform_storage: str = "platform-storage"
    platform_object_storage: str = "platform-object-storage"
    platform_registry: str = "platform-registry"
    platform_monitoring: str = "platform-monitoring"
    platform_secrets: str = "platform-secrets"
    platform_reports: str = "platform-reports"
    platform_disk_api: str = "platform-disk-api"


@dataclass(frozen=True)
class HelmChartVersions:
    platform: str
    obs_csi_driver: str


@dataclass(frozen=True)
class DockerRegistry:
    url: URL
    email: str
    username: str
    password: str


@dataclass(frozen=True)
class Config:
    log_level: str
    retries: int
    backoff: int
    kube_config: KubeConfig
    helm_stable_repo: HelmRepo
    helm_release_names: HelmReleaseNames
    helm_chart_names: HelmChartNames
    helm_chart_versions: HelmChartVersions
    helm_service_account: str
    platform_auth_url: URL
    platform_ingress_auth_url: URL
    platform_config_url: URL
    platform_api_url: URL
    platform_namespace: str
    consul_url: URL
    consul_installed: bool

    @classmethod
    def load_from_env(cls, env: Optional[Mapping[str, str]] = None) -> "Config":
        env = env or os.environ
        platform_release_name = "platform"
        return cls(
            log_level=(env.get("NP_CONTROLLER_LOG_LEVEL") or "INFO").upper(),
            retries=int(env.get("NP_CONTROLLER_RETRIES") or "3"),
            backoff=int(env.get("NP_CONTROLLER_BACKOFF") or "60"),
            kube_config=KubeConfig(
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
                auth_token_path=cls._convert_to_path(
                    env.get("NP_KUBE_AUTH_TOKEN_PATH")
                ),
                auth_token=env.get("NP_KUBE_AUTH_TOKEN"),
            ),
            helm_stable_repo=HelmRepo(
                name=HelmRepoName.STABLE, url=URL(env["NP_HELM_STABLE_REPO_URL"])
            ),
            helm_service_account=env["NP_HELM_SERVICE_ACCOUNT_NAME"],
            helm_release_names=HelmReleaseNames(
                platform=platform_release_name,
                obs_csi_driver="platform-obs-csi-driver",
            ),
            helm_chart_names=HelmChartNames(),
            helm_chart_versions=HelmChartVersions(
                platform=env["NP_HELM_PLATFORM_CHART_VERSION"],
                obs_csi_driver=env["NP_HELM_OBS_CSI_DRIVER_CHART_VERSION"],
            ),
            platform_auth_url=URL(env["NP_PLATFORM_AUTH_URL"]),
            platform_ingress_auth_url=URL(env["NP_PLATFORM_INGRESS_AUTH_URL"]),
            platform_config_url=URL(env["NP_PLATFORM_CONFIG_URL"]),
            platform_api_url=URL(env["NP_PLATFORM_API_URL"]),
            platform_namespace=env["NP_PLATFORM_NAMESPACE"],
            consul_url=URL(env["NP_CONSUL_URL"]),
            consul_installed=env.get("NP_CONSUL_INSTALLED", "false").lower() == "true",
        )

    @classmethod
    def _convert_to_path(cls, value: Optional[str]) -> Optional[Path]:
        return Path(value) if value else None


class Cluster(Dict[str, Any]):
    @property
    def name(self) -> str:
        return self["name"]

    @property
    def cloud_provider_type(self) -> str:
        return self["cloud_provider"]["type"]

    @property
    def acme_environment(self) -> str:
        return self["ingress"]["acme_environment"]

    @property
    def dns_zone_name(self) -> str:
        return self["dns"]["zone_name"]


class StorageSpec(Dict[str, Any]):
    def __init__(self, spec: Dict[str, Any]) -> None:
        super().__init__(spec)

        self._spec = defaultdict(self._default_factory, spec)

    @classmethod
    def _default_factory(cls) -> Dict[str, Any]:
        return defaultdict(cls._default_factory)

    def get_storage_type(self, *supported_types: str) -> str:
        try:
            return next(t for t in supported_types if t in self)
        except StopIteration:
            return ""

    @property
    def storage_size(self) -> str:
        return self._spec["kubernetes"]["persistence"].get("size", "")

    @property
    def storage_class_name(self) -> str:
        return self._spec["kubernetes"]["persistence"].get("storageClassName", "")

    @property
    def nfs_server(self) -> str:
        return self._spec["nfs"].get("server", "")

    @property
    def nfs_path(self) -> str:
        return self._spec["nfs"].get("path", "/")

    @property
    def gcs_bucket_name(self) -> str:
        return self._spec["gcs"].get("bucket", "")

    @property
    def azure_file_storage_account_name(self) -> str:
        return self._spec["azureFile"].get("storageAccountName", "")

    @property
    def azure_file_storage_account_key(self) -> str:
        return self._spec["azureFile"].get("storageAccountKey", "")

    @property
    def azure_file_share_name(self) -> str:
        return self._spec["azureFile"].get("shareName", "")


@dataclass(frozen=True)
class GcpConfig:
    project: str
    region: str
    service_account_key: str
    service_account_key_base64: str
    storage_type: str
    storage_size: str = ""
    storage_class_name: str = ""
    storage_nfs_server: str = ""
    storage_nfs_path: str = "/"
    storage_gcs_bucket_name: str = ""


@dataclass(frozen=True)
class AwsConfig:
    region: str
    registry_url: URL
    storage_type: str
    storage_size: str = ""
    storage_class_name: str = ""
    storage_nfs_server: str = ""
    storage_nfs_path: str = "/"
    role_arn: str = ""


@dataclass(frozen=True)
class AzureConfig:
    region: str
    registry_url: URL
    registry_username: str
    registry_password: str
    storage_share_name: str
    blob_storage_account_name: str
    blob_storage_account_key: str
    storage_type: str
    storage_size: str = ""
    storage_class_name: str = ""
    storage_nfs_server: str = ""
    storage_nfs_path: str = "/"
    storage_account_name: str = ""
    storage_account_key: str = ""


@dataclass(frozen=True)
class OnPremConfig:
    registry_storage_class_name: str
    registry_storage_size: str
    blob_storage_region: str
    blob_storage_access_key: str
    blob_storage_secret_key: str
    blob_storage_class_name: str
    blob_storage_size: str
    kubelet_port: int
    http_node_port: int
    https_node_port: int
    storage_type: str
    storage_size: str = ""
    storage_class_name: str = ""
    storage_nfs_server: str = ""
    storage_nfs_path: str = "/"


@dataclass(frozen=True)
class PlatformConfig:
    auth_url: URL
    ingress_auth_url: URL
    config_url: URL
    api_url: URL
    token: str
    cluster_name: str
    cloud_provider: str
    namespace: str
    docker_config_secret_create: bool
    docker_config_secret_name: str
    service_account_name: str
    image_pull_secret_names: Sequence[str]
    pre_pull_images: Sequence[str]
    standard_storage_class_name: str
    kubernetes_version: str
    kubernetes_public_url: URL
    kubernetes_node_labels: LabelsConfig
    dns_zone_id: str
    dns_zone_name: str
    dns_zone_name_servers: Sequence[str]
    ingress_url: URL
    ingress_registry_url: URL
    ingress_metrics_url: URL
    ingress_acme_environment: str
    ingress_controller_enabled: bool
    ingress_public_ips: Sequence[IPv4Address]
    ingress_cors_origins: Sequence[str]
    disks_storage_limit_per_user_gb: int
    service_traefik_name: str
    jobs_namespace_create: bool
    jobs_namespace: str
    jobs_node_pools: Sequence[Dict[str, Any]]
    jobs_schedule_timeout_s: float
    jobs_schedule_scale_up_timeout_s: float
    jobs_resource_pool_types: Sequence[Dict[str, Any]]
    jobs_resource_presets: Sequence[Dict[str, Any]]
    jobs_priority_class_name: str
    jobs_host_template: str
    jobs_fallback_host: str
    jobs_service_account_name: str
    storage_pvc_name: str
    helm_repo: HelmRepo
    docker_registry: DockerRegistry
    grafana_username: str
    grafana_password: str
    consul_url: URL
    consul_install: bool
    monitoring_logs_bucket_name: str = ""
    monitoring_metrics_bucket_name: str = ""
    monitoring_metrics_storage_class_name: str = ""
    monitoring_metrics_storage_size: str = ""
    gcp: Optional[GcpConfig] = None
    aws: Optional[AwsConfig] = None
    azure: Optional[AzureConfig] = None
    on_prem: Optional[OnPremConfig] = None

    def create_dns_config(
        self,
        traefik_service: Optional[Dict[str, Any]] = None,
        aws_traefik_lb: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not traefik_service and not self.ingress_public_ips:
            return None
        result: Dict[str, Any] = {
            "zone_id": self.dns_zone_id,
            "zone_name": self.dns_zone_name,
            "name_servers": self.dns_zone_name_servers,
            "a_records": [],
        }
        if self.ingress_public_ips:
            ips = [str(ip) for ip in self.ingress_public_ips]
            result["a_records"].extend(
                (
                    {"name": self.dns_zone_name, "ips": ips},
                    {"name": f"*.jobs.{self.dns_zone_name}", "ips": ips},
                    {"name": f"registry.{self.dns_zone_name}", "ips": ips},
                    {"name": f"metrics.{self.dns_zone_name}", "ips": ips},
                )
            )
        elif self.aws and traefik_service:
            traefik_host = traefik_service["status"]["loadBalancer"]["ingress"][0][
                "hostname"
            ]
            assert aws_traefik_lb
            traefik_zone_id = aws_traefik_lb["CanonicalHostedZoneNameID"]
            result["a_records"].extend(
                (
                    {
                        "name": self.dns_zone_name,
                        "dns_name": traefik_host,
                        "zone_id": traefik_zone_id,
                    },
                    {
                        "name": f"*.jobs.{self.dns_zone_name}",
                        "dns_name": traefik_host,
                        "zone_id": traefik_zone_id,
                    },
                    {
                        "name": f"registry.{self.dns_zone_name}",
                        "dns_name": traefik_host,
                        "zone_id": traefik_zone_id,
                    },
                    {
                        "name": f"metrics.{self.dns_zone_name}",
                        "dns_name": traefik_host,
                        "zone_id": traefik_zone_id,
                    },
                )
            )
        elif traefik_service:
            traefik_host = traefik_service["status"]["loadBalancer"]["ingress"][0]["ip"]
            result["a_records"].extend(
                (
                    {"name": self.dns_zone_name, "ips": [traefik_host]},
                    {"name": f"*.jobs.{self.dns_zone_name}", "ips": [traefik_host]},
                    {"name": f"registry.{self.dns_zone_name}", "ips": [traefik_host]},
                    {"name": f"metrics.{self.dns_zone_name}", "ips": [traefik_host]},
                )
            )
        return result

    def create_cluster_config(
        self,
        service_account_secret: Dict[str, Any],
        traefik_service: Optional[Dict[str, Any]] = None,
        aws_traefik_lb: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "storage": {
                "url": str(self.ingress_url / "api/v1/storage"),
                "pvc": {"name": self.storage_pvc_name},
            },
            "orchestrator": {
                "kubernetes": {
                    "url": str(self.kubernetes_public_url),
                    "ca_data": service_account_secret["data"]["ca.crt"],
                    "auth_type": "token",
                    "token": service_account_secret["data"]["token"],
                    "namespace": self.jobs_namespace,
                    "node_label_gpu": self.kubernetes_node_labels.accelerator,
                    "node_label_preemptible": self.kubernetes_node_labels.preemptible,
                    "node_label_job": self.kubernetes_node_labels.job,
                    "node_label_node_pool": self.kubernetes_node_labels.node_pool,
                    "job_pod_priority_class_name": self.jobs_priority_class_name,
                },
                "is_http_ingress_secure": True,
                "job_hostname_template": self.jobs_host_template,
                "job_fallback_hostname": str(self.jobs_fallback_host),
                "job_schedule_timeout_s": self.jobs_schedule_timeout_s,
                "job_schedule_scale_up_timeout_s": (
                    self.jobs_schedule_scale_up_timeout_s
                ),
                "resource_pool_types": self.jobs_resource_pool_types,
                "resource_presets": self._create_resource_presets(),
                "pre_pull_images": self.pre_pull_images,
            },
        }
        dns = self.create_dns_config(
            traefik_service=traefik_service, aws_traefik_lb=aws_traefik_lb
        )
        if dns:
            result["dns"] = dns
        if self.azure:
            result["orchestrator"]["kubernetes"][
                "job_pod_preemptible_toleration_key"
            ] = "kubernetes.azure.com/scalesetpriority"
        return result

    def _create_resource_presets(self) -> Sequence[Dict[str, Any]]:
        result = []
        for preset in self.jobs_resource_presets:
            new_preset = deepcopy(preset)
            new_preset.pop("resource_affinity", None)
            result.append(new_preset)
        return result


class PlatformConfigFactory:
    def __init__(self, config: Config) -> None:
        self._config = config

    def create(self, platform_body: bodies.Body, cluster: Cluster) -> "PlatformConfig":
        ingress_host = cluster["dns"]["zone_name"].strip(".")
        standard_storage_class_name = (
            f"{self._config.platform_namespace}-standard-topology-aware"
        )
        kubernetes_spec = platform_body["spec"]["kubernetes"]
        kubernetes_node_labels = kubernetes_spec.get("nodeLabels", {})
        tpu_network = None
        if cluster.cloud_provider_type == "gcp":
            tpu_network = (
                IPv4Network(kubernetes_spec["tpuIPv4CIDR"])
                if "tpuIPv4CIDR" in kubernetes_spec
                else None
            )
        if cluster.cloud_provider_type == "on_prem":
            standard_storage_class_name = kubernetes_spec["standardStorageClassName"]
        monitoring_spec = platform_body["spec"]["monitoring"]
        monitoring_metrics_spec = platform_body["spec"]["monitoring"].get("metrics", {})
        monitoring_metrics_default_storage_size = ""
        if cluster.cloud_provider_type == "on_prem":
            monitoring_metrics_default_storage_size = "10Gi"
        docker_config_secret_spec = kubernetes_spec.get("dockerConfigSecret", {})
        docker_config_secret_name = docker_config_secret_spec.get(
            "name", f"{self._config.platform_namespace}-docker-config"
        )
        service_account_spec = kubernetes_spec.get("serviceAccount", {})
        image_pull_secrets = service_account_spec.get("imagePullSecrets", [])
        image_pull_secret_names = [secret["name"] for secret in image_pull_secrets]
        if docker_config_secret_name not in image_pull_secret_names:
            image_pull_secret_names.append(docker_config_secret_name)
        jobs_namespace_spec = kubernetes_spec.get("jobsNamespace", {})
        jobs_namespace = jobs_namespace_spec.get(
            "name", self._config.platform_namespace + "-jobs"
        )
        return PlatformConfig(
            auth_url=self._config.platform_auth_url,
            ingress_auth_url=self._config.platform_ingress_auth_url,
            config_url=self._config.platform_config_url,
            api_url=self._config.platform_api_url,
            token=platform_body["spec"]["token"],
            cluster_name=platform_body["metadata"]["name"],
            cloud_provider=cluster.cloud_provider_type,
            namespace=self._config.platform_namespace,
            docker_config_secret_create=docker_config_secret_spec.get("create", True),
            docker_config_secret_name=docker_config_secret_name,
            service_account_name="default",
            image_pull_secret_names=image_pull_secret_names,
            pre_pull_images=cluster["orchestrator"].get("pre_pull_images", ()),
            standard_storage_class_name=standard_storage_class_name,
            kubernetes_version=self._config.kube_config.version,
            kubernetes_public_url=URL(kubernetes_spec["publicUrl"]),
            kubernetes_node_labels=LabelsConfig(
                job=kubernetes_node_labels.get("job", LabelsConfig.job),
                node_pool=kubernetes_node_labels.get(
                    "nodePool", LabelsConfig.node_pool
                ),
                accelerator=kubernetes_node_labels.get(
                    "accelerator", LabelsConfig.accelerator
                ),
                preemptible=kubernetes_node_labels.get(
                    "preemptible", LabelsConfig.preemptible
                ),
            ),
            dns_zone_id=cluster["dns"]["zone_id"],
            dns_zone_name=cluster["dns"]["zone_name"],
            dns_zone_name_servers=cluster["dns"]["name_servers"],
            ingress_url=URL(f"https://{ingress_host}"),
            ingress_registry_url=URL(f"https://registry.{ingress_host}"),
            ingress_metrics_url=URL(f"https://metrics.{ingress_host}"),
            ingress_acme_environment=cluster.acme_environment,
            ingress_controller_enabled=kubernetes_spec.get("ingressController", {}).get(
                "enabled", True
            ),
            ingress_public_ips=[
                IPv4Address(ip) for ip in kubernetes_spec.get("ingressPublicIPs", [])
            ],
            ingress_cors_origins=cluster["ingress"].get("cors_origins", ()),
            disks_storage_limit_per_user_gb=cluster["disks"][
                "storage_limit_per_user_gb"
            ],
            service_traefik_name=f"{self._config.platform_namespace}-traefik",
            jobs_namespace_create=jobs_namespace_spec.get("create", True),
            jobs_namespace=jobs_namespace,
            jobs_node_pools=self._create_node_pools(
                cluster["cloud_provider"]["node_pools"]
            ),
            jobs_resource_pool_types=self._update_tpu_network(
                cluster["orchestrator"].get("resource_pool_types", ()),
                tpu_network,
            ),
            jobs_resource_presets=cluster["orchestrator"].get("resource_presets", ()),
            jobs_schedule_timeout_s=cluster["orchestrator"]["job_schedule_timeout_s"],
            jobs_schedule_scale_up_timeout_s=cluster["orchestrator"][
                "job_schedule_scale_up_timeout_s"
            ],
            jobs_priority_class_name=f"{self._config.platform_namespace}-job",
            jobs_host_template=f"{{job_id}}.jobs.{ingress_host}",
            jobs_fallback_host=cluster["orchestrator"]["job_fallback_hostname"],
            jobs_service_account_name=f"{self._config.platform_namespace}-jobs",
            monitoring_logs_bucket_name=(
                monitoring_spec["logs"]["blobStorage"]["bucket"]
            ),
            monitoring_metrics_bucket_name=(
                monitoring_metrics_spec.get("blobStorage", {}).get("bucket", "")
            ),
            monitoring_metrics_storage_class_name=(
                monitoring_metrics_spec.get("kubernetes", {})
                .get("persistence", {})
                .get("storageClassName", "")
            ),
            monitoring_metrics_storage_size=(
                monitoring_metrics_spec.get("kubernetes", {})
                .get("persistence", {})
                .get("size", monitoring_metrics_default_storage_size)
            ),
            storage_pvc_name=f"{self._config.platform_namespace}-storage",
            helm_repo=self._create_helm_repo(cluster),
            docker_registry=self._create_docker_registry(cluster),
            grafana_username=cluster["credentials"]["grafana"]["username"],
            grafana_password=cluster["credentials"]["grafana"]["password"],
            consul_url=self._config.consul_url,
            consul_install=not self._config.consul_installed,
            gcp=(
                self._create_gcp(platform_body["spec"], cluster)
                if cluster.cloud_provider_type == "gcp"
                else None
            ),
            aws=(
                self._create_aws(platform_body["spec"], cluster)
                if cluster.cloud_provider_type == "aws"
                else None
            ),
            azure=(
                self._create_azure(platform_body["spec"], cluster)
                if cluster.cloud_provider_type == "azure"
                else None
            ),
            on_prem=(
                self._create_on_prem(platform_body["spec"])
                if cluster.cloud_provider_type == "on_prem"
                else None
            ),
        )

    @classmethod
    def _create_helm_repo(cls, cluster: Cluster) -> HelmRepo:
        neuro_helm = cluster["credentials"]["neuro_helm"]
        return HelmRepo(
            name=HelmRepoName.NEURO,
            url=URL(neuro_helm["url"]),
            username=neuro_helm["username"],
            password=neuro_helm["password"],
        )

    @classmethod
    def _create_docker_registry(cls, cluster: Cluster) -> DockerRegistry:
        neuro_registry = cluster["credentials"]["neuro_registry"]
        return DockerRegistry(
            url=URL(neuro_registry["url"]),
            email=neuro_registry["email"],
            username=neuro_registry["username"],
            password=neuro_registry["password"],
        )

    @classmethod
    def _create_gcp(cls, spec: bodies.Spec, cluster: Cluster) -> GcpConfig:
        cloud_provider = cluster["cloud_provider"]
        iam_gcp_spec = spec.get("iam", {}).get("gcp")
        service_account_key = cls._base64_decode(
            iam_gcp_spec.get("serviceAccountKeyBase64")
        ) or json.dumps(cloud_provider["credentials"])
        service_account_key_base64 = iam_gcp_spec.get(
            "serviceAccountKeyBase64"
        ) or cls._base64_encode(json.dumps(cloud_provider["credentials"]))
        storage_spec = StorageSpec(spec["storage"])
        storage_type = storage_spec.get_storage_type("kubernetes", "nfs", "gcs")
        assert storage_type, "Invalid storage type"
        return GcpConfig(
            project=cloud_provider["project"],
            region=cloud_provider["region"],
            service_account_key=service_account_key,
            service_account_key_base64=service_account_key_base64,
            storage_type=storage_type,
            storage_size=storage_spec.storage_size,
            storage_class_name=storage_spec.storage_class_name,
            storage_nfs_server=storage_spec.nfs_server,
            storage_nfs_path=storage_spec.nfs_path,
            storage_gcs_bucket_name=storage_spec.gcs_bucket_name,
        )

    @classmethod
    def _create_aws(cls, spec: bodies.Spec, cluster: Cluster) -> "AwsConfig":
        registry_url = URL(spec["registry"]["aws"]["url"])
        if not registry_url.scheme:
            registry_url = URL(f"https://{registry_url!s}")
        storage_spec = StorageSpec(spec["storage"])
        storage_type = storage_spec.get_storage_type("kubernetes", "nfs")
        assert storage_type, "Invalid storage type"
        return AwsConfig(
            region=cluster["cloud_provider"]["region"],
            role_arn=spec.get("iam", {}).get("aws", {}).get("roleArn", ""),
            registry_url=registry_url,
            storage_type=storage_type,
            storage_size=storage_spec.storage_size,
            storage_class_name=storage_spec.storage_class_name,
            storage_nfs_server=storage_spec.nfs_server,
            storage_nfs_path=storage_spec.nfs_path,
        )

    @classmethod
    def _create_azure(cls, spec: bodies.Spec, cluster: Cluster) -> AzureConfig:
        registry_url = URL(spec["registry"]["azure"]["url"])
        if not registry_url.scheme:
            registry_url = URL(f"https://{registry_url!s}")
        storage_spec = StorageSpec(spec["storage"])
        storage_type = storage_spec.get_storage_type("kubernetes", "nfs", "azureFile")
        assert storage_type, "Invalid storage type"
        return AzureConfig(
            region=cluster["cloud_provider"]["region"],
            registry_url=registry_url,
            registry_username=spec["registry"]["azure"]["username"],
            registry_password=spec["registry"]["azure"]["password"],
            storage_type=storage_type,
            storage_size=storage_spec.storage_size,
            storage_class_name=storage_spec.storage_class_name,
            storage_nfs_server=storage_spec.nfs_server,
            storage_nfs_path=storage_spec.nfs_path,
            storage_account_name=storage_spec.azure_file_storage_account_name,
            storage_account_key=storage_spec.azure_file_storage_account_key,
            storage_share_name=storage_spec.azure_file_share_name,
            blob_storage_account_name=spec["blobStorage"]["azure"][
                "storageAccountName"
            ],
            blob_storage_account_key=spec["blobStorage"]["azure"]["storageAccountKey"],
        )

    @classmethod
    def _create_on_prem(cls, spec: bodies.Spec) -> OnPremConfig:
        kubernetes_spec = spec["kubernetes"]
        storage_spec = StorageSpec(spec["storage"])
        storage_type = storage_spec.get_storage_type("kubernetes", "nfs")
        assert storage_type, "Invalid storage type"
        registry_persistence = spec["registry"]["kubernetes"]["persistence"]
        blob_storage_persistence = spec["blobStorage"]["kubernetes"]["persistence"]
        return OnPremConfig(
            registry_storage_class_name=registry_persistence["storageClassName"],
            registry_storage_size=registry_persistence.get("size") or "10Gi",
            storage_type=storage_type,
            storage_class_name=storage_spec.storage_class_name,
            storage_size=storage_spec.storage_size or "10Gi",
            storage_nfs_server=storage_spec.nfs_server,
            storage_nfs_path=storage_spec.nfs_path,
            blob_storage_region="minio",
            blob_storage_access_key="minio_access_key",
            blob_storage_secret_key="minio_secret_key",
            blob_storage_class_name=blob_storage_persistence["storageClassName"],
            blob_storage_size=blob_storage_persistence.get("size") or "10Gi",
            kubelet_port=int(kubernetes_spec["nodePorts"]["kubelet"]),
            http_node_port=int(kubernetes_spec["nodePorts"]["http"]),
            https_node_port=int(kubernetes_spec["nodePorts"]["https"]),
        )

    @classmethod
    def _base64_encode(cls, value: str) -> str:
        return b64encode(value.encode("utf-8")).decode("utf-8")

    @classmethod
    def _base64_decode(cls, value: Optional[str]) -> str:
        if not value:
            return ""
        return b64decode(value.encode("utf-8")).decode("utf-8")

    @classmethod
    def _update_tpu_network(
        cls,
        resource_pools_types: Sequence[Dict[str, Any]],
        tpu_network: Optional[IPv4Network],
    ) -> Sequence[Dict[str, Any]]:
        resource_pools_types = copy.deepcopy(resource_pools_types)
        for rpt in resource_pools_types:
            if "tpu" in rpt and tpu_network:
                rpt["tpu"]["ipv4_cidr_block"] = str(tpu_network)
        return resource_pools_types

    @classmethod
    def _create_node_pools(
        cls, node_pools: Sequence[Mapping[str, Any]]
    ) -> Sequence[Dict[str, Any]]:
        return [cls._create_node_pool(np) for np in node_pools]

    @classmethod
    def _create_node_pool(cls, node_pool: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "name": node_pool["name"],
            "idleSize": node_pool.get("idle_size", 0),
            "cpu": node_pool["available_cpu"],
            "gpu": node_pool.get("gpu", 0),
        }
