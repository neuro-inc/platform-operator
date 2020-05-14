import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Optional

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
            ),
            helm_chart_names=HelmChartNames(),
            helm_chart_versions=HelmChartVersions(
                platform=env["NP_HELM_PLATFORM_CHART_VERSION"],
                obs_csi_driver=env["NP_HELM_OBS_CSI_DRIVER_CHART_VERSION"],
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
