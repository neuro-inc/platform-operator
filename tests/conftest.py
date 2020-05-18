import uuid
from typing import Any, Callable, Dict

import pytest
from yarl import URL

from platform_operator.models import (
    DockerRegistry,
    GcpConfig,
    HelmRepo,
    HelmRepoName,
    PlatformConfig,
)


@pytest.fixture
def cluster_name() -> str:
    return str(uuid.uuid4())


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
def gcp_platform_config(
    cluster_name: str, resource_pool_type_factory: Callable[[str], Dict[str, Any]]
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
        kubernetes_url=URL("https://kubernetes.default"),
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
        jobs_resource_pool_types=[resource_pool_type_factory("192.168.0.0/16")],
        jobs_fallback_url=URL("default.jobs-dev.neu.ro"),
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
