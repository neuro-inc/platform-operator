import copy
import json
import os
from base64 import b64encode
from dataclasses import dataclass
from enum import Enum
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from kopf.structs import bodies
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
    kubernetes_public_ip: IPv4Address
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
    kubernetes_public_url: URL
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
    jobs_fallback_host: str
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
            traefik_host = str(self.on_prem.kubernetes_public_ip)
            ssh_auth_host = str(self.on_prem.kubernetes_public_ip)
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

    def create_cluster_config(
        self, service_account_secret: Dict[str, Any]
    ) -> Dict[str, Any]:
        result = {
            "name": self.cluster_name,
            "storage": {
                "url": str(self.ingress_url / "api/v1/storage"),
                "pvc": {"name": self.storage_pvc_name},
            },
            "registry": {
                "url": str(self.ingress_registry_url),
                "email": f"{self.cluster_name}@neuromation.io",
            },
            "orchestrator": {
                "kubernetes": {
                    "url": str(self.kubernetes_public_url),
                    "ca_data": service_account_secret["data"]["ca.crt"],
                    "auth_type": "token",
                    "token": service_account_secret["data"]["token"],
                    "namespace": self.jobs_namespace,
                    "node_label_gpu": "cloud.google.com/gke-accelerator",
                    "node_label_preemptible": "cloud.google.com/gke-preemptible",
                    "node_label_job": self.jobs_label,
                    "job_pod_priority_class_name": self.jobs_priority_class_name,
                },
                "is_http_ingress_secure": True,
                "job_hostname_template": self.jobs_host_template,
                "job_fallback_hostname": str(self.jobs_fallback_host),
                "resource_pool_types": self.jobs_resource_pool_types,
            },
            "ssh": {"server": self.ingress_ssh_auth_server},
            "monitoring": {"url": str(self.ingress_url / "api/v1/jobs")},
        }
        return result


class PlatformConfigFactory:
    def __init__(self, config: Config) -> None:
        self._config = config

    def create(self, platform_body: bodies.Body, cluster: Cluster) -> "PlatformConfig":
        ingress_host = cluster["dns"]["zone_name"].strip(".")
        ingress_ssh_auth_server = f"ssh-auth.{ingress_host}"
        standard_storage_class_name = (
            f"{self._config.platform_namespace}-standard-topology-aware"
        )
        kubernetes_spec = platform_body["spec"]["kubernetes"]
        tpu_network = None
        if cluster.cloud_provider_type == "gcp":
            tpu_network = (
                IPv4Network(kubernetes_spec["tpuIPv4CIDR"])
                if "tpuIPv4CIDR" in kubernetes_spec
                else None
            )
        return PlatformConfig(
            auth_url=self._config.platform_auth_url,
            api_url=self._config.platform_api_url,
            token=platform_body["spec"]["token"],
            cluster_name=platform_body["metadata"]["name"],
            cloud_provider=cluster.cloud_provider_type,
            namespace=self._config.platform_namespace,
            image_pull_secret_name=f"{self._config.platform_namespace}-docker-config",
            standard_storage_class_name=standard_storage_class_name,
            kubernetes_public_url=URL(kubernetes_spec["publicUrl"]),
            dns_zone_id=cluster["dns"]["zone_id"],
            dns_zone_name=cluster["dns"]["zone_name"],
            dns_zone_name_servers=cluster["dns"]["name_servers"],
            ingress_url=URL(f"https://{ingress_host}"),
            ingress_registry_url=URL(f"https://registry.{ingress_host}"),
            ingress_ssh_auth_server=ingress_ssh_auth_server,
            ingress_acme_environment=cluster.acme_environment,
            service_traefik_name=f"{self._config.platform_namespace}-traefik",
            service_ssh_auth_name="ssh-auth",
            jobs_namespace=self._config.platform_jobs_namespace,
            jobs_label="platform.neuromation.io/job",
            jobs_node_pools=[
                # TODO: add node pools config
            ],
            jobs_resource_pool_types=self._update_tpu_network(
                cluster["orchestrator"].get("resource_pool_types", ()), tpu_network,
            ),
            jobs_priority_class_name=f"{self._config.platform_namespace}-job",
            jobs_host_template=f"{{job_id}}.jobs.{ingress_host}",
            jobs_fallback_host=cluster["orchestrator"]["job_fallback_hostname"],
            jobs_service_account_name=f"{self._config.platform_namespace}-jobs",
            storage_pvc_name=f"{self._config.platform_namespace}-storage",
            helm_repo=self._create_helm_repo(cluster),
            docker_registry=self._create_docker_registry(cluster),
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
        service_account_key_base64 = iam_gcp_spec.get(
            "serviceAccountKeyBase64"
        ) or cls._base64_encode(json.dumps(cloud_provider["credentials"]))
        storage_spec = spec["storage"]
        assert "gcs" in storage_spec or "nfs" in storage_spec
        return GcpConfig(
            project=cloud_provider["project"],
            region=cloud_provider["region"],
            service_account_key_base64=service_account_key_base64,
            storage_type="gcs" if "gcs" in storage_spec else "nfs",
            storage_nfs_server=storage_spec.get("nfs", {}).get("server", ""),
            storage_nfs_path=storage_spec.get("nfs", {}).get("path", "/"),
            storage_gcs_bucket_name=storage_spec.get("gcs", {}).get("bucket", ""),
        )

    @classmethod
    def _create_aws(cls, spec: bodies.Spec, cluster: Cluster) -> "AwsConfig":
        iam_roles = spec.get("iam", {}).get("aws", {}).get("roles", {})
        registry_url = URL(spec["registry"]["aws"]["url"])
        if not registry_url.scheme:
            registry_url = URL(f"https://{registry_url!s}")
        return AwsConfig(
            region=cluster["cloud_provider"]["region"],
            role_ecr_arn=iam_roles.get("ecrRoleArn", ""),
            role_auto_scaling_arn=iam_roles.get("autoScalingRoleArn", ""),
            role_s3_arn=iam_roles.get("s3RoleArn", ""),
            registry_url=registry_url,
            storage_nfs_server=spec["storage"]["nfs"]["server"],
            storage_nfs_path=spec["storage"]["nfs"].get("path", "/"),
        )

    @classmethod
    def _create_azure(cls, spec: bodies.Spec, cluster: Cluster) -> AzureConfig:
        registry_url = URL(spec["registry"]["azure"]["url"])
        if not registry_url.scheme:
            registry_url = URL(f"https://{registry_url!s}")
        return AzureConfig(
            region=cluster["cloud_provider"]["region"],
            registry_url=registry_url,
            registry_username=spec["registry"]["azure"]["username"],
            registry_password=spec["registry"]["azure"]["password"],
            storage_account_name=spec["storage"]["azureFile"]["storageAccountName"],
            storage_account_key=spec["storage"]["azureFile"]["storageAccountKey"],
            storage_share_name=spec["storage"]["azureFile"]["shareName"],
            blob_storage_account_name=spec["blobStorage"]["azure"][
                "storageAccountName"
            ],
            blob_storage_account_key=spec["blobStorage"]["azure"]["storageAccountKey"],
        )

    @classmethod
    def _base64_encode(cls, value: str) -> str:
        return b64encode(value.encode("utf-8")).decode("utf-8")

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
