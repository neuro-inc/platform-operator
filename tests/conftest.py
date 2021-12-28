from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import replace
from ipaddress import IPv4Address
from typing import Any

import kopf
import pytest
from yarl import URL

from platform_operator.models import (
    BucketsConfig,
    BucketsProvider,
    CloudProvider,
    Cluster,
    Config,
    DockerConfig,
    HelmChartNames,
    HelmChartVersions,
    HelmReleaseNames,
    HelmRepo,
    IngressServiceType,
    KubeClientAuthType,
    KubeConfig,
    LabelsConfig,
    MetricsStorageType,
    MonitoringConfig,
    PlatformConfig,
    RegistryConfig,
    RegistryProvider,
    StorageConfig,
    StorageType,
)

pytest_plugins = ["tests.integration.kube", "tests.integration.aws"]


@pytest.fixture
def config() -> Config:
    return Config(
        node_name="minikube",
        log_level="DEBUG",
        retries=3,
        backoff=60,
        kube_config=KubeConfig(
            version="1.16.10",
            url=URL("https://kubernetes.default"),
            auth_type=KubeClientAuthType.NONE,
        ),
        helm_release_names=HelmReleaseNames(
            platform="platform", obs_csi_driver="platform-obs-csi-driver"
        ),
        helm_chart_names=HelmChartNames(),
        helm_chart_versions=HelmChartVersions(platform="1.0.0", obs_csi_driver="2.0.0"),
        platform_auth_url=URL("https://dev.neu.ro"),
        platform_ingress_auth_url=URL("https://platformingressauth"),
        platform_config_url=URL("https://dev.neu.ro"),
        platform_config_watch_interval_s=0.1,
        platform_admin_url=URL("https://dev.neu.ro"),
        platform_api_url=URL("https://dev.neu.ro"),
        platform_namespace="platform",
        consul_url=URL("http://consul:8500"),
        consul_installed=True,
        is_standalone=False,
    )


@pytest.fixture
def cluster_name() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def resource_pool_type_factory() -> Callable[..., dict[str, Any]]:
    def _factory(name: str, tpu_ipv4_cidr_block: str = "") -> dict[str, Any]:
        result = {
            "name": name,
            "is_preemptible": False,
            "min_size": 0,
            "max_size": 1,
            "cpu": 1,
            "available_cpu": 1,
            "memory_mb": 1024,
            "available_memory_mb": 1024,
            "gpu": 1,
            "gpu_model": "nvidia-tesla-k80",
            "presets": [{"name": "gpu-small", "cpu": 1, "memory_mb": 1024, "gpu": 1}],
        }
        if tpu_ipv4_cidr_block:
            result["tpu"] = {"ipv4_cidr_block": tpu_ipv4_cidr_block}
        return result

    return _factory


@pytest.fixture
def resource_preset_factory() -> Callable[[], dict[str, Any]]:
    def _factory() -> dict[str, Any]:
        return {
            "name": "gpu-small",
            "cpu": 1,
            "memory_mb": 1024,
            "gpu": 1,
            "gpu_model": "nvidia-tesla-k80",
            "resource_affinity": ["gpu"],
        }

    return _factory


@pytest.fixture
def cluster_factory(
    resource_pool_type_factory: Callable[..., dict[str, Any]],
    resource_preset_factory: Callable[[], dict[str, Any]],
) -> Callable[..., Cluster]:
    def _factory(name: str, resource_pool_name: str) -> Cluster:
        payload = {
            "name": name,
            "storage": {"url": f"https://{name}.org.neu.ro/api/v1/storage"},
            "registry": {"url": f"https://registry.{name}.org.neu.ro"},
            "orchestrator": {
                "job_hostname_template": f"{{job_id}}.jobs.{name}.org.neu.ro",
                "is_http_ingress_secure": True,
                "resource_pool_types": [resource_pool_type_factory(resource_pool_name)],
                "resource_presets": [resource_preset_factory()],
                "job_fallback_hostname": "default.jobs-dev.neu.ro",
                "job_schedule_timeout_s": 60,
                "job_schedule_scale_up_timeout_s": 30,
                "pre_pull_images": ["neuromation/base"],
                "allow_privileged_mode": True,
                "idle_jobs": [
                    {
                        "name": "miner",
                        "count": 1,
                        "image": "miner",
                        "resources": {"cpu_m": 1000, "memory_mb": 1024},
                    }
                ],
            },
            "monitoring": {"url": f"https://{name}.org.neu.ro/api/v1/jobs"},
            "credentials": {
                "neuro_registry": {
                    "username": name,
                    "password": "password",
                    "url": "https://neuro.io",
                    "email": f"{name}@neuromation.io",
                },
                "neuro_helm": {
                    "url": "https://ghcr.io/neuro-inc/helm-charts",
                    "username": name,
                    "password": "password",
                },
                "neuro": {
                    "token": "token",
                    "url": "https://dev.neu.ro",
                },
                "grafana": {"username": "admin", "password": "grafana_password"},
                "sentry": {"public_dsn": "https://sentry", "sample_rate": 0.1},
                "docker_hub": {
                    "username": name,
                    "password": "password",
                    "url": "https://index.docker.io/v1/",
                    "email": f"{name}@neuromation.io",
                },
            },
            "dns": {"name": f"{name}.org.neu.ro"},
            "disks": {"storage_limit_per_user_gb": 10240},
            "ingress": {
                "acme_environment": "staging",
                "cors_origins": [
                    "https://release--neuro-web.netlify.app",
                    "https://app.neu.ro",
                ],
            },
            "buckets": {"disable_creation": False},
        }
        return Cluster(payload)

    return _factory


@pytest.fixture
def gcp_cluster(cluster_name: str, cluster_factory: Callable[..., Cluster]) -> Cluster:
    cluster = cluster_factory(cluster_name, "n1-highmem-8")
    cluster["orchestrator"]["resource_pool_types"][0]["tpu"] = {}
    return cluster


@pytest.fixture
def aws_cluster(cluster_name: str, cluster_factory: Callable[..., Cluster]) -> Cluster:
    return cluster_factory(cluster_name, "p2.xlarge")


@pytest.fixture
def azure_cluster(
    cluster_name: str, cluster_factory: Callable[..., Cluster]
) -> Cluster:
    return cluster_factory(cluster_name, "Standard_NC6")


@pytest.fixture
def on_prem_cluster(
    cluster_name: str, cluster_factory: Callable[..., Cluster]
) -> Cluster:
    cluster = cluster_factory(cluster_name, "gpu")
    cluster["credentials"]["minio"] = {
        "username": "username",
        "password": "password",
    }
    return cluster


@pytest.fixture
def vcd_cluster(cluster_name: str, cluster_factory: Callable[..., Cluster]) -> Cluster:
    cluster = cluster_factory(cluster_name, "gpu")
    cluster["credentials"]["minio"] = {
        "username": "username",
        "password": "password",
    }
    return cluster


@pytest.fixture
def gcp_platform_body(cluster_name: str) -> kopf.Body:
    payload = {
        "apiVersion": "neuromation.io/v1",
        "kind": "Platform",
        "metadata": {"name": cluster_name},
        "spec": {
            "token": "token",
            "kubernetes": {
                "provider": "gcp",
                "standardStorageClassName": "platform-standard-topology-aware",
                "tpuIPv4CIDR": "192.168.0.0/16",
            },
            "iam": {"gcp": {"serviceAccountKeyBase64": "e30="}},
            "registry": {"gcp": {"project": "project"}},
            "storages": [{"nfs": {"server": "192.168.0.3", "path": "/"}}],
            "blobStorage": {"gcp": {"project": "project"}},
            "monitoring": {
                "logs": {"blobStorage": {"bucket": "job-logs"}},
                "metrics": {
                    "region": "us-central1",
                    "blobStorage": {"bucket": "job-metrics"},
                },
            },
            "disks": {
                "kubernetes": {
                    "persistence": {
                        "storageClassName": "platform-disk",
                    }
                }
            },
        },
    }
    return kopf.Body(payload)


@pytest.fixture
def aws_platform_body(cluster_name: str) -> kopf.Body:
    payload = {
        "apiVersion": "neuromation.io/v1",
        "kind": "Platform",
        "metadata": {"name": cluster_name},
        "spec": {
            "token": "token",
            "kubernetes": {
                "provider": "aws",
                "standardStorageClassName": "platform-standard-topology-aware",
            },
            "registry": {"aws": {"accountId": "platform", "region": "us-east-1"}},
            "storages": [{"nfs": {"server": "192.168.0.3", "path": "/"}}],
            "blobStorage": {"aws": {"region": "us-east-1"}},
            "monitoring": {
                "logs": {"blobStorage": {"bucket": "job-logs"}},
                "metrics": {
                    "region": "us-east-1",
                    "blobStorage": {"bucket": "job-metrics"},
                },
            },
            "disks": {
                "kubernetes": {
                    "persistence": {
                        "storageClassName": "platform-disk",
                    }
                }
            },
        },
    }
    return kopf.Body(payload)


@pytest.fixture
def azure_platform_body(cluster_name: str) -> kopf.Body:
    payload = {
        "apiVersion": "neuromation.io/v1",
        "kind": "Platform",
        "metadata": {"name": cluster_name},
        "spec": {
            "token": "token",
            "kubernetes": {
                "provider": "azure",
                "standardStorageClassName": "platform-standard-topology-aware",
            },
            "registry": {
                "azure": {
                    "url": "platform.azurecr.io",
                    "username": "admin",
                    "password": "admin-password",
                }
            },
            "storages": [
                {
                    "azureFile": {
                        "storageAccountName": "accountName1",
                        "storageAccountKey": "accountKey1",
                        "shareName": "share",
                    }
                }
            ],
            "blobStorage": {
                "azure": {
                    "storageAccountName": "accountName2",
                    "storageAccountKey": "accountKey2",
                },
            },
            "monitoring": {
                "logs": {"blobStorage": {"bucket": "job-logs"}},
                "metrics": {
                    "region": "westus",
                    "blobStorage": {"bucket": "job-metrics"},
                },
            },
            "disks": {
                "kubernetes": {
                    "persistence": {
                        "storageClassName": "platform-disk",
                    }
                }
            },
        },
    }
    return kopf.Body(payload)


@pytest.fixture
def on_prem_platform_body(cluster_name: str) -> kopf.Body:
    payload = {
        "apiVersion": "neuromation.io/v1",
        "kind": "Platform",
        "metadata": {"name": cluster_name},
        "spec": {
            "token": "token",
            "kubernetes": {
                "provider": "kubeadm",
                "standardStorageClassName": "standard",
            },
            "ingressController": {
                "publicIPs": ["192.168.0.3"],
            },
            "registry": {
                "kubernetes": {
                    "persistence": {
                        "storageClassName": "registry-standard",
                        "size": "100Gi",
                    }
                }
            },
            "storages": [
                {
                    "kubernetes": {
                        "persistence": {
                            "storageClassName": "storage-standard",
                            "size": "1000Gi",
                        }
                    }
                }
            ],
            "blobStorage": {
                "kubernetes": {
                    "persistence": {
                        "storageClassName": "blob-storage-standard",
                        "size": "10Gi",
                    }
                }
            },
            "monitoring": {
                "logs": {"blobStorage": {"bucket": "job-logs"}},
                "metrics": {
                    "kubernetes": {
                        "persistence": {
                            "storageClassName": "metrics-standard",
                            "size": "100Gi",
                        }
                    }
                },
            },
            "disks": {
                "kubernetes": {
                    "persistence": {
                        "storageClassName": "openebs-cstor",
                    }
                }
            },
        },
    }
    return kopf.Body(payload)


@pytest.fixture
def vcd_platform_body(on_prem_platform_body: kopf.Body) -> kopf.Body:
    return on_prem_platform_body


@pytest.fixture
def gcp_platform_config(
    cluster_name: str,
    resource_pool_type_factory: Callable[..., dict[str, Any]],
    resource_preset_factory: Callable[[], dict[str, Any]],
) -> PlatformConfig:
    return PlatformConfig(
        release_name="platform",
        auth_url=URL("https://dev.neu.ro"),
        config_url=URL("https://dev.neu.ro"),
        admin_url=URL("https://dev.neu.ro"),
        api_url=URL("https://dev.neu.ro"),
        token="token",
        cluster_name=cluster_name,
        namespace="platform",
        service_account_name="default",
        image_pull_secret_names=[
            "platform-docker-config",
            "platform-docker-hub-config",
        ],
        pre_pull_images=["neuromation/base"],
        standard_storage_class_name="platform-standard-topology-aware",
        kubernetes_provider=CloudProvider.GCP,
        kubernetes_version="1.16.10",
        kubelet_port=10250,
        node_labels=LabelsConfig(
            job="platform.neuromation.io/job",
            node_pool="platform.neuromation.io/nodepool",
            accelerator="platform.neuromation.io/accelerator",
            preemptible="platform.neuromation.io/preemptible",
        ),
        jobs_namespace="platform-jobs",
        jobs_node_pools=[{"name": "n1-highmem-8", "idleSize": 0, "cpu": 1, "gpu": 1}],
        jobs_resource_pool_types=[
            resource_pool_type_factory("n1-highmem-8", "192.168.0.0/16")
        ],
        jobs_resource_presets=[resource_preset_factory()],
        jobs_fallback_host="default.jobs-dev.neu.ro",
        jobs_host_template=f"{{job_id}}.jobs.{cluster_name}.org.neu.ro",
        jobs_internal_host_template="{job_id}.platform-jobs",
        jobs_priority_class_name="platform-job",
        jobs_schedule_timeout_s=60,
        jobs_schedule_scale_up_timeout_s=30,
        jobs_allow_privileged_mode=True,
        idle_jobs=[
            {
                "name": "miner",
                "count": 1,
                "image": "miner",
                "resources": {"cpu_m": 1000, "memory_mb": 1024},
            }
        ],
        ingress_dns_name=f"{cluster_name}.org.neu.ro",
        ingress_url=URL(f"https://{cluster_name}.org.neu.ro"),
        ingress_auth_url=URL("https://platformingressauth"),
        ingress_registry_url=URL(f"https://registry.{cluster_name}.org.neu.ro"),
        ingress_metrics_url=URL(f"https://metrics.{cluster_name}.org.neu.ro"),
        ingress_acme_environment="staging",
        ingress_controller_install=True,
        ingress_controller_replicas=2,
        ingress_public_ips=[],
        ingress_cors_origins=[
            "https://release--neuro-web.netlify.app",
            "https://app.neu.ro",
        ],
        ingress_service_type=IngressServiceType.LOAD_BALANCER,
        ingress_service_name="traefik",
        ingress_node_port_http=None,
        ingress_node_port_https=None,
        ingress_host_port_http=None,
        ingress_host_port_https=None,
        ingress_namespaces=["platform", "platform-jobs"],
        ingress_ssl_cert_data="",
        ingress_ssl_cert_key_data="",
        storages=[
            StorageConfig(
                type=StorageType.NFS,
                nfs_server="192.168.0.3",
                nfs_export_path="/",
            )
        ],
        registry=RegistryConfig(provider=RegistryProvider.GCP, gcp_project="project"),
        buckets=BucketsConfig(
            provider=BucketsProvider.GCP,
            gcp_location="us",
            gcp_project="project",
        ),
        monitoring=MonitoringConfig(
            logs_bucket_name="job-logs",
            metrics_storage_type=MetricsStorageType.BUCKETS,
            metrics_region="us-central1",
            metrics_bucket_name="job-metrics",
        ),
        disks_storage_limit_per_user_gb=10240,
        disks_storage_class_name="platform-disk",
        helm_repo=HelmRepo(
            url=URL("https://ghcr.io/neuro-inc/helm-charts"),
            username=cluster_name,
            password="password",
        ),
        grafana_username="admin",
        grafana_password="grafana_password",
        consul_url=URL("http://consul:8500"),
        consul_install=False,
        sentry_dsn=URL("https://sentry"),
        sentry_sample_rate=0.1,
        gcp_service_account_key="{}",
        gcp_service_account_key_base64="e30=",
        docker_config=DockerConfig(
            url=URL("https://neuro.io"),
            email=f"{cluster_name}@neuromation.io",
            username=cluster_name,
            password="password",
            create_secret=True,
            secret_name="platform-docker-config",
        ),
        docker_hub_config=DockerConfig(
            url=URL("https://index.docker.io/v1/"),
            email=f"{cluster_name}@neuromation.io",
            username=cluster_name,
            password="password",
            secret_name="platform-docker-hub-config",
            create_secret=True,
        ),
    )


@pytest.fixture
def aws_platform_config(
    gcp_platform_config: PlatformConfig,
    resource_pool_type_factory: Callable[..., dict[str, Any]],
) -> PlatformConfig:
    return replace(
        gcp_platform_config,
        gcp_service_account_key="",
        gcp_service_account_key_base64="",
        kubernetes_provider=CloudProvider.AWS,
        jobs_node_pools=[{"name": "p2.xlarge", "idleSize": 0, "cpu": 1.0, "gpu": 1}],
        jobs_resource_pool_types=[resource_pool_type_factory("p2.xlarge")],
        registry=RegistryConfig(
            provider=RegistryProvider.AWS,
            aws_account_id="platform",
            aws_region="us-east-1",
        ),
        buckets=BucketsConfig(
            provider=BucketsProvider.AWS,
            aws_region="us-east-1",
        ),
        monitoring=MonitoringConfig(
            logs_bucket_name="job-logs",
            metrics_storage_type=MetricsStorageType.BUCKETS,
            metrics_region="us-east-1",
            metrics_bucket_name="job-metrics",
        ),
    )


@pytest.fixture
def azure_platform_config(
    gcp_platform_config: PlatformConfig,
    resource_pool_type_factory: Callable[..., dict[str, Any]],
) -> PlatformConfig:
    return replace(
        gcp_platform_config,
        gcp_service_account_key="",
        gcp_service_account_key_base64="",
        kubernetes_provider=CloudProvider.AZURE,
        jobs_node_pools=[{"name": "Standard_NC6", "idleSize": 0, "cpu": 1.0, "gpu": 1}],
        jobs_resource_pool_types=[resource_pool_type_factory("Standard_NC6")],
        storages=[
            StorageConfig(
                type=StorageType.AZURE_fILE,
                azure_storage_account_name="accountName1",
                azure_storage_account_key="accountKey1",
                azure_share_name="share",
            )
        ],
        registry=RegistryConfig(
            provider=RegistryProvider.AZURE,
            azure_url=URL("https://platform.azurecr.io"),
            azure_username="admin",
            azure_password="admin-password",
        ),
        buckets=BucketsConfig(
            provider=BucketsProvider.AZURE,
            azure_storage_account_name="accountName2",
            azure_storage_account_key="accountKey2",
        ),
        monitoring=MonitoringConfig(
            logs_bucket_name="job-logs",
            metrics_storage_type=MetricsStorageType.BUCKETS,
            metrics_region="westus",
            metrics_bucket_name="job-metrics",
        ),
    )


@pytest.fixture
def on_prem_platform_config(
    gcp_platform_config: PlatformConfig,
    resource_pool_type_factory: Callable[..., dict[str, Any]],
    cluster_name: str,
) -> PlatformConfig:
    return replace(
        gcp_platform_config,
        gcp_service_account_key="",
        gcp_service_account_key_base64="",
        ingress_public_ips=[IPv4Address("192.168.0.3")],
        standard_storage_class_name="standard",
        kubernetes_provider="kubeadm",
        jobs_node_pools=[{"name": "gpu", "idleSize": 0, "cpu": 1.0, "gpu": 1}],
        jobs_resource_pool_types=[resource_pool_type_factory("gpu")],
        disks_storage_class_name="openebs-cstor",
        storages=[
            StorageConfig(
                type=StorageType.KUBERNETES,
                storage_size="1000Gi",
                storage_class_name="storage-standard",
            )
        ],
        registry=RegistryConfig(
            provider=RegistryProvider.DOCKER,
            docker_registry_install=True,
            docker_registry_url=URL("http://platform-docker-registry:5000"),
            docker_registry_username="",
            docker_registry_password="",
            docker_registry_storage_class_name="registry-standard",
            docker_registry_storage_size="100Gi",
        ),
        buckets=BucketsConfig(
            provider=BucketsProvider.MINIO,
            minio_install=True,
            minio_public_url=URL(f"https://blob.{cluster_name}.org.neu.ro"),
            minio_url=URL("http://platform-minio:9000"),
            minio_region="minio",
            minio_access_key="username",
            minio_secret_key="password",
            minio_storage_class_name="blob-storage-standard",
            minio_storage_size="10Gi",
        ),
        monitoring=MonitoringConfig(
            logs_bucket_name="job-logs",
            metrics_storage_type=MetricsStorageType.KUBERNETES,
            metrics_storage_class_name="metrics-standard",
            metrics_storage_size="100Gi",
        ),
    )


@pytest.fixture
def vcd_platform_config(on_prem_platform_config: PlatformConfig) -> PlatformConfig:
    return replace(on_prem_platform_config, kubernetes_provider="kubeadm")
