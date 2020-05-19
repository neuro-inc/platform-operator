import os
from dataclasses import dataclass
from enum import Enum
from ipaddress import IPv4Address
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from yarl import URL


class KubeClientAuthType(str, Enum):
    NONE = "none"
    TOKEN = "token"
    CERTIFICATE = "certificate"


@dataclass(frozen=True)
class KubeConfig:
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
    nfs_server: str


@dataclass(frozen=True)
class HelmChartNames:
    obs_csi_driver: str = "obs-csi-driver"
    docker_registry: str = "docker-registry"
    nfs_server: str = "nfs-server"
    consul: str = "consul"
    traefik: str = "traefik"
    elasticsearch: str = "elasticsearch"
    elasticsearch_curator: str = "elasticsearch-curator"
    fluent_bit: str = "fluent-bit"
    cluster_autoscaler: str = "cluster-autoscaler"
    platform: str = "platform"
    platform_storage: str = "platform-storage"
    platform_object_storage: str = "platform-object-storage"
    platform_registry: str = "platform-registry"
    platform_monitoring: str = "platform-monitoring"
    platform_ssh_auth: str = "ssh-auth"


@dataclass(frozen=True)
class HelmChartVersions:
    platform: str
    obs_csi_driver: str
    nfs_server: str


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
    platform_url: URL
    platform_auth_url: URL
    platform_api_url: URL
    platform_namespace: str
    platform_jobs_namespace: str

    @classmethod
    def load_from_env(cls, env: Optional[Mapping[str, str]] = None) -> "Config":
        env = env or os.environ
        platform_url = URL(env["NP_PLATFORM_URL"])
        return cls(
            log_level=(env.get("NP_CONTROLLER_LOG_LEVEL") or "INFO").upper(),
            retries=int(env.get("NP_CONTROLLER_RETRIES") or "3"),
            backoff=int(env.get("NP_CONTROLLER_BACKOFF") or "60"),
            kube_config=KubeConfig(
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
                platform=env["NP_PLATFORM_NAMESPACE"],
                obs_csi_driver=env["NP_PLATFORM_NAMESPACE"] + "-obs-csi-driver",
                nfs_server=env["NP_PLATFORM_NAMESPACE"] + "-nfs-server",
            ),
            helm_chart_names=HelmChartNames(),
            helm_chart_versions=HelmChartVersions(
                platform=env["NP_HELM_PLATFORM_CHART_VERSION"],
                obs_csi_driver=env["NP_HELM_OBS_CSI_DRIVER_CHART_VERSION"],
                nfs_server=env["NP_HELM_NFS_SERVER_CHART_VERSION"],
            ),
            platform_url=platform_url,
            platform_auth_url=platform_url,
            platform_api_url=platform_url / "api/v1",
            platform_namespace=env["NP_PLATFORM_NAMESPACE"],
            platform_jobs_namespace=env["NP_PLATFORM_NAMESPACE"] + "-jobs",
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
        if "acme_environment" in self["lb"]:
            return self["lb"]["acme_environment"]
        return self["lb"]["http"]["acme_environment"]

    @property
    def dns_zone_name(self) -> str:
        return self["dns"]["zone_name"]


@dataclass(frozen=True)
class GcpConfig:
    project: str
    region: str
    service_account_key_base64: str
    storage_type: str
    storage_nfs_server: str = ""
    storage_nfs_path: str = ""
    storage_gcs_bucket_name: str = ""


@dataclass(frozen=True)
class AwsConfig:
    region: str
    registry_url: URL
    storage_nfs_server: str
    storage_nfs_path: str
    role_ecr_arn: str = ""
    role_s3_arn: str = ""
    role_auto_scaling_arn: str = ""


@dataclass(frozen=True)
class AzureConfig:
    region: str
    registry_url: URL
    registry_username: str
    registry_password: str
    storage_account_name: str
    storage_account_key: str
    storage_share_name: str
    blob_storage_account_name: str
    blob_storage_account_key: str


@dataclass(frozen=True)
class OnPremConfig:
    external_ip: IPv4Address
    masters_count: int
    registry_storage_class_name: str
    registry_storage_size: str
    storage_class_name: str
    storage_size: str
    kubelet_port: int
    http_node_port: int
    https_node_port: int
    ssh_auth_node_port: int


@dataclass(frozen=True)
class PlatformConfig:
    auth_url: URL
    api_url: URL
    token: str
    cluster_name: str
    cloud_provider: str
    namespace: str
    image_pull_secret_name: str
    standard_storage_class_name: str
    kubernetes_url: URL
    dns_zone_id: str
    dns_zone_name: str
    dns_zone_name_servers: Sequence[str]
    ingress_url: URL
    ingress_registry_url: URL
    ingress_ssh_auth_server: str
    ingress_acme_environment: str
    service_traefik_name: str
    service_ssh_auth_name: str
    jobs_namespace: str
    jobs_label: str
    jobs_node_pools: Sequence[Dict[str, Any]]
    jobs_resource_pool_types: Sequence[Dict[str, Any]]
    jobs_priority_class_name: str
    jobs_host_template: str
    jobs_fallback_url: URL
    jobs_service_account_name: str
    storage_pvc_name: str
    helm_repo: HelmRepo
    docker_registry: DockerRegistry
    gcp: Optional[GcpConfig] = None
    aws: Optional[AwsConfig] = None
    azure: Optional[AzureConfig] = None
    on_prem: Optional[OnPremConfig] = None

    def create_dns_config(
        self,
        traefik_service: Dict[str, Any],
        ssh_auth_service: Dict[str, Any],
        aws_traefik_lb: Optional[Dict[str, Any]] = None,
        aws_ssh_auth_lb: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        traefik_zone_id = ""
        ssh_auth_zone_id = ""
        if self.aws:
            traefik_host = traefik_service["status"]["loadBalancer"]["ingress"][0][
                "hostname"
            ]
            ssh_auth_host = ssh_auth_service["status"]["loadBalancer"]["ingress"][0][
                "hostname"
            ]
            assert aws_traefik_lb
            assert aws_ssh_auth_lb
            traefik_zone_id = aws_traefik_lb["CanonicalHostedZoneNameID"]
            ssh_auth_zone_id = aws_ssh_auth_lb["CanonicalHostedZoneNameID"]
        elif self.on_prem:
            traefik_host = str(self.on_prem.external_ip)
            ssh_auth_host = str(self.on_prem.external_ip)
        else:
            traefik_host = traefik_service["status"]["loadBalancer"]["ingress"][0]["ip"]
            ssh_auth_host = ssh_auth_service["status"]["loadBalancer"]["ingress"][0][
                "ip"
            ]
        result: Dict[str, Any] = {
            "zone_id": self.dns_zone_id,
            "zone_name": self.dns_zone_name,
            "name_servers": self.dns_zone_name_servers,
            "a_records": [],
        }
        if traefik_zone_id:
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
                )
            )
        else:
            result["a_records"].extend(
                (
                    {"name": self.dns_zone_name, "ips": [traefik_host]},
                    {"name": f"*.jobs.{self.dns_zone_name}", "ips": [traefik_host]},
                    {"name": f"registry.{self.dns_zone_name}", "ips": [traefik_host]},
                )
            )
        if ssh_auth_zone_id:
            result["a_records"].append(
                {
                    "name": f"ssh-auth.{self.dns_zone_name}",
                    "dns_name": ssh_auth_host,
                    "zone_id": ssh_auth_zone_id,
                }
            )
        else:
            result["a_records"].append(
                {"name": f"ssh-auth.{self.dns_zone_name}", "ips": [ssh_auth_host]}
            )
        return result
