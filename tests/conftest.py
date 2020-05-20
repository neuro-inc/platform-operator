import uuid
from dataclasses import replace
from ipaddress import IPv4Address
from typing import Any, Callable, Dict

import pytest
from kopf.structs import bodies
from yarl import URL

from platform_operator.models import (
    AwsConfig,
    AzureConfig,
    Cluster,
    Config,
    DockerRegistry,
    GcpConfig,
    HelmChartNames,
    HelmChartVersions,
    HelmReleaseNames,
    HelmRepo,
    HelmRepoName,
    KubeClientAuthType,
    KubeConfig,
    OnPremConfig,
    PlatformConfig,
)


@pytest.fixture
def config() -> Config:
    return Config(
        log_level="DEBUG",
        retries=3,
        backoff=60,
        kube_config=KubeConfig(
            url=URL("https://kubernetes.default"), auth_type=KubeClientAuthType.NONE,
        ),
        helm_stable_repo=HelmRepo(
            name="stable", url=URL("https://kubernetes-charts.storage.googleapis.com"),
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
        platform_url=URL("https://dev.neu.ro"),
        platform_auth_url=URL("https://dev.neu.ro"),
        platform_api_url=URL("https://dev.neu.ro/api/v1"),
        platform_namespace="platform",
        platform_jobs_namespace="platform-jobs",
    )


@pytest.fixture
def cluster_name() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def node_pool_factory() -> Callable[[str], Dict[str, Any]]:
    def _factory(machine_type: str) -> Dict[str, Any]:
        return {
            "machine_type": machine_type,
            "min_size": 0,
            "max_size": 1,
            "cpu": 1.0,
            "available_cpu": 1.0,
            "memory_mb": 1024,
            "available_memory_mb": 1024,
            "gpu": 1,
            "gpu_model": "nvidia-tesla-k80",
        }

    return _factory


@pytest.fixture
def resource_pool_type_factory() -> Callable[[], Dict[str, Any]]:
    def _factory(tpu_ipv4_cidr_block: str = "") -> Dict[str, Any]:
        result = {
            "is_preemptible": False,
            "min_size": 0,
            "max_size": 1,
            "cpu": 1,
            "memory_mb": 1024,
            "gpu": 1,
            "gpu_model": "nvidia-tesla-k80",
            "presets": [{"name": "gpu-small", "cpu": 1, "memory_mb": 1024, "gpu": 1}],
        }
        if tpu_ipv4_cidr_block:
            result["tpu"] = {"ipv4_cidr_block": tpu_ipv4_cidr_block}
        return result

    return _factory


@pytest.fixture
def cluster_factory(
    resource_pool_type_factory: Callable[[], Dict[str, Any]]
) -> Callable[[str], Cluster]:
    def _factory(name: str) -> Cluster:
        payload = {
            "name": name,
            "storage": {
                "url": f"https://{name}.org.neu.ro/api/v1/storage",
                "pvc": {"name": "platform-storage"},
            },
            "registry": {
                "url": f"https://registry.{name}.org.neu.ro",
                "email": f"{name}@neuromation.io",
            },
            "orchestrator": {
                "job_hostname_template": f"{{job_id}}.jobs.{name}.org.neu.ro",
                "is_http_ingress_secure": True,
                "resource_pool_types": [resource_pool_type_factory()],
                "kubernetes": {},
                "job_fallback_hostname": "default.jobs-dev.neu.ro",
            },
            "ssh": {"server": f"ssh-auth.{name}.org.neu.ro"},
            "monitoring": {"url": f"https://{name}.org.neu.ro/api/v1/jobs"},
            "credentials": {
                "neuro_registry": {
                    "username": name,
                    "password": "password",
                    "url": "https://neuro-docker-local-public.jfrog.io",
                    "email": f"{name}@neuromation.io",
                },
                "neuro_helm": {
                    "username": name,
                    "password": "password",
                    "url": "https://neuro.jfrog.io/neuro/helm-virtual-public",
                },
                "neuro": {
                    "registry_token": "token",
                    "storage_token": "token",
                    "compute_token": "token",
                    "cluster_token": "token",
                    "url": "https://dev.neu.ro",
                },
            },
            "dns": {
                "zone_id": "/hostedzone/id",
                "zone_name": f"{name}.org.neu.ro.",
                "name_servers": ["192.168.0.2"],
            },
            "lb": {"acme_environment": "staging"},
        }
        return Cluster(payload)

    return _factory


@pytest.fixture
def gcp_cluster(
    cluster_name: str,
    cluster_factory: Callable[[str], Cluster],
    node_pool_factory: Callable[[str], Dict[str, Any]],
) -> Cluster:
    cluster = cluster_factory(cluster_name)
    cluster["cloud_provider"] = {
        "type": "gcp",
        "location_type": "zonal",
        "region": "us-central1",
        "zone": "us-central1-a",
        "project": "project",
        "credentials": {
            # XXX: Add other stab credentials as needed
            "client_email": "test-acc@test-project.iam.gserviceaccount.com"
        },
        "node_pools": [node_pool_factory("n1-highmem-8")],
        "storage": {"tier": "PREMIUM", "capacity_tb": 5, "backend": "filestore"},
    }
    return cluster


@pytest.fixture
def gcp_platform_body(cluster_name: str) -> bodies.Body:
    payload = {
        "apiVersion": "v1",
        "kind": "Platform",
        "metadata": {"name": cluster_name},
        "spec": {
            "token": "token",
            "kubernetes": {"publicUrl": "https://kubernetes.default"},
            "iam": {"gcp": {"serviceAccountKeyBase64": "e30="}},
            "storage": {"nfs": {"server": "192.168.0.3", "path": "/"}},
        },
    }
    return bodies.Body(payload)


@pytest.fixture
def gcp_platform_config(
    cluster_name: str, resource_pool_type_factory: Callable[[], Dict[str, Any]]
) -> PlatformConfig:
    return PlatformConfig(
        auth_url=URL("https://dev.neu.ro"),
        api_url=URL("https://dev.neu.ro/api/v1"),
        token="token",
        cluster_name=cluster_name,
        cloud_provider="gcp",
        namespace="platform",
        image_pull_secret_name="platform-docker-config",
        standard_storage_class_name="platform-standard-topology-aware",
        kubernetes_public_url=URL("https://kubernetes.default"),
        dns_zone_id="/hostedzone/id",
        dns_zone_name=f"{cluster_name}.org.neu.ro.",
        dns_zone_name_servers=["192.168.0.2"],
        jobs_namespace="platform-jobs",
        jobs_label="platform.neuromation.io/job",
        jobs_node_pools=[
            {
                "name": "n1-highmem-8-1xk80-non-preemptible",
                "idleSize": 0,
                "cpu": 1.0,
                "gpu": 1,
            }
        ],
        jobs_resource_pool_types=[resource_pool_type_factory()],
        jobs_fallback_host="default.jobs-dev.neu.ro",
        jobs_host_template=f"{{job_id}}.jobs.{cluster_name}.org.neu.ro",
        jobs_priority_class_name="platform-job",
        jobs_service_account_name="platform-jobs",
        ingress_url=URL(f"https://{cluster_name}.org.neu.ro"),
        ingress_registry_url=URL(f"https://registry.{cluster_name}.org.neu.ro"),
        ingress_ssh_auth_server=f"ssh-auth.{cluster_name}.org.neu.ro",
        ingress_acme_environment="staging",
        service_traefik_name="platform-traefik",
        service_ssh_auth_name="ssh-auth",
        storage_pvc_name="platform-storage",
        helm_repo=HelmRepo(
            name=HelmRepoName.NEURO,
            url=URL("https://neuro.jfrog.io/neuro/helm-virtual-public"),
            username=cluster_name,
            password="password",
        ),
        docker_registry=DockerRegistry(
            url=URL("https://neuro-docker-local-public.jfrog.io"),
            email=f"{cluster_name}@neuromation.io",
            username=cluster_name,
            password="password",
        ),
        gcp=GcpConfig(
            project="project",
            region="us-central1",
            service_account_key_base64="e30=",
            storage_type="nfs",
            storage_nfs_server="192.168.0.3",
            storage_nfs_path="/",
        ),
    )


@pytest.fixture
def aws_platform_config(
    gcp_platform_config: PlatformConfig,
    resource_pool_type_factory: Callable[[], Dict[str, Any]],
) -> PlatformConfig:
    return replace(
        gcp_platform_config,
        gcp=None,
        cloud_provider="aws",
        jobs_node_pools=[
            {
                "name": "p2-xlarge-1xk80-non-preemptible",
                "idleSize": 0,
                "cpu": 1.0,
                "gpu": 1,
            }
        ],
        jobs_resource_pool_types=[resource_pool_type_factory()],
        aws=AwsConfig(
            region="us-east-1",
            registry_url=URL("https://platform.dkr.ecr.us-east-1.amazonaws.com"),
            storage_nfs_server="192.168.0.3",
            storage_nfs_path="/",
        ),
    )


@pytest.fixture
def azure_platform_config(
    gcp_platform_config: PlatformConfig,
    resource_pool_type_factory: Callable[[], Dict[str, Any]],
) -> PlatformConfig:
    return replace(
        gcp_platform_config,
        gcp=None,
        cloud_provider="azure",
        jobs_node_pools=[
            {
                "name": "Standard_NC6-1xk80-non-preemptible",
                "idleSize": 0,
                "cpu": 1.0,
                "gpu": 1,
            }
        ],
        jobs_resource_pool_types=[resource_pool_type_factory()],
        azure=AzureConfig(
            region="westus",
            registry_url=URL("https://platform.azurecr.io"),
            registry_username="admin",
            registry_password="admin-password",
            storage_account_name="accountName1",
            storage_account_key="accountKey1",
            storage_share_name="share",
            blob_storage_account_name="accountName2",
            blob_storage_account_key="accountKey2",
        ),
    )


@pytest.fixture
def on_prem_platform_config(
    gcp_platform_config: PlatformConfig,
    resource_pool_type_factory: Callable[[], Dict[str, Any]],
) -> PlatformConfig:
    return replace(
        gcp_platform_config,
        gcp=None,
        standard_storage_class_name="standard",
        cloud_provider="on_prem",
        ingress_ssh_auth_server=(
            f"ssh-auth.{gcp_platform_config.cluster_name}.org.neu.ro:30022"
        ),
        jobs_node_pools=[
            {"name": "gpu-1xk80-non-preemptible", "idleSize": 0, "cpu": 1.0, "gpu": 1}
        ],
        jobs_resource_pool_types=[resource_pool_type_factory()],
        on_prem=OnPremConfig(
            kubernetes_public_ip=IPv4Address("192.168.0.3"),
            masters_count=1,
            registry_storage_class_name="registry-standard",
            registry_storage_size="100Gi",
            storage_class_name="storage-standard",
            storage_size="1000Gi",
            kubelet_port=10250,
            http_node_port=30080,
            https_node_port=30443,
            ssh_auth_node_port=30022,
        ),
    )
