import uuid
from dataclasses import replace
from ipaddress import IPv4Address
from typing import Any, Callable, Dict

import kopf
import pytest
from yarl import URL

from platform_operator.models import (
    AwsConfig,
    AzureConfig,
    Cluster,
    Config,
    DockerRegistry,
    EMCECSCredentials,
    GcpConfig,
    HelmChartNames,
    HelmChartVersions,
    HelmReleaseNames,
    HelmRepo,
    HelmRepoName,
    KubeClientAuthType,
    KubeConfig,
    LabelsConfig,
    OnPremConfig,
    OpenStackCredentials,
    PlatformConfig,
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
            version="1.14.9",
            url=URL("https://kubernetes.default"),
            auth_type=KubeClientAuthType.NONE,
        ),
        helm_stable_repo=HelmRepo(
            name="stable", url=URL("https://kubernetes-charts.storage.googleapis.com")
        ),
        helm_release_names=HelmReleaseNames(
            platform="platform", obs_csi_driver="platform-obs-csi-driver"
        ),
        helm_chart_names=HelmChartNames(),
        helm_chart_versions=HelmChartVersions(platform="1.0.0", obs_csi_driver="2.0.0"),
        helm_service_account="default",
        platform_auth_url=URL("https://dev.neu.ro"),
        platform_ingress_auth_url=URL("https://platformingressauth"),
        platform_config_url=URL("https://dev.neu.ro"),
        platform_config_watch_interval_s=0.1,
        platform_api_url=URL("https://dev.neu.ro"),
        platform_namespace="platform",
        consul_url=URL("http://consul:8500"),
        consul_installed=True,
    )


@pytest.fixture
def cluster_name() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def node_pool_factory() -> Callable[[str], Dict[str, Any]]:
    def _factory(machine_type: str) -> Dict[str, Any]:
        return {
            "name": machine_type + "-name",
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
            "name": "gpu",
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
def resource_preset_factory() -> Callable[[], Dict[str, Any]]:
    def _factory() -> Dict[str, Any]:
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
    resource_pool_type_factory: Callable[[], Dict[str, Any]],
    resource_preset_factory: Callable[[], Dict[str, Any]],
) -> Callable[[str], Cluster]:
    def _factory(name: str) -> Cluster:
        payload = {
            "name": name,
            "storage": {"url": f"https://{name}.org.neu.ro/api/v1/storage"},
            "registry": {"url": f"https://registry.{name}.org.neu.ro"},
            "orchestrator": {
                "job_hostname_template": f"{{job_id}}.jobs.{name}.org.neu.ro",
                "is_http_ingress_secure": True,
                "resource_pool_types": [resource_pool_type_factory()],
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
                    "username": name,
                    "password": "password",
                    "url": "https://neuro.jfrog.io/neuro/helm-virtual-public",
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
    cluster["orchestrator"]["resource_pool_types"][0]["tpu"] = {}
    return cluster


@pytest.fixture
def aws_cluster(
    cluster_name: str,
    cluster_factory: Callable[[str], Cluster],
    node_pool_factory: Callable[[str], Dict[str, Any]],
) -> Cluster:
    cluster = cluster_factory(cluster_name)
    cluster["cloud_provider"] = {
        "type": "aws",
        "region": "us-east-1",
        "zones": ["us-east-1a", "us-east-1b"],
        "vpc_id": "test-vpc",
        "credentials": {
            "access_key_id": "access_key_id",
            "secret_access_key": "secret_access_key",
        },
        "node_pools": [node_pool_factory("p2.xlarge")],
        "storage": {
            "performance_mode": "generalPurpose",
            "throughput_mode": "bursting",
        },
    }
    return cluster


@pytest.fixture
def azure_cluster(
    cluster_name: str,
    cluster_factory: Callable[[str], Cluster],
    node_pool_factory: Callable[[str], Dict[str, Any]],
) -> Cluster:
    cluster = cluster_factory(cluster_name)
    cluster["cloud_provider"] = {
        "type": "azure",
        "region": "westus",
        "resource_group": "platform-resource-group",
        "credentials": {
            "subscription_id": "client_subscription_id",
            "tenant_id": "client_tenant_id",
            "client_id": "client_client_id",
            "client_secret": "client_client_secret",
        },
        "node_pools": [node_pool_factory("Standard_NC6")],
        "storage": {
            "tier": "Premium",
            "replication_type": "LRS",
            "file_share_size_gib": 100,
        },
    }
    return cluster


@pytest.fixture
def on_prem_cluster(
    cluster_name: str,
    cluster_factory: Callable[[str], Cluster],
    node_pool_factory: Callable[[str], Dict[str, Any]],
) -> Cluster:
    cluster = cluster_factory(cluster_name)
    cluster["cloud_provider"] = {
        "type": "on_prem",
        "kubernetes_url": "https://192.168.0.2",
        "credentials": {"token": "kubernetes-token", "ca_data": "kubernetes-ca-data"},
        "node_pools": [node_pool_factory("gpu")],
    }
    cluster["credentials"]["minio"] = {
        "username": "username",
        "password": "password",
    }
    return cluster


@pytest.fixture
def vcd_cluster(
    cluster_name: str,
    cluster_factory: Callable[[str], Cluster],
    node_pool_factory: Callable[[str], Dict[str, Any]],
) -> Cluster:
    cluster = cluster_factory(cluster_name)
    cluster["cloud_provider"] = {
        "type": "vcd_mts",
        "node_pools": [node_pool_factory("gpu")],
    }
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
                "tpuIPv4CIDR": "192.168.0.0/16",
            },
            "iam": {"gcp": {"serviceAccountKeyBase64": "e30="}},
            "storages": [{"nfs": {"server": "192.168.0.3", "path": "/"}}],
            "monitoring": {
                "logs": {"blobStorage": {"bucket": "job-logs"}},
                "metrics": {"blobStorage": {"bucket": "job-metrics"}},
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
            "registry": {"aws": {"url": "platform.dkr.ecr.us-east-1.amazonaws.com"}},
            "storages": [{"nfs": {"server": "192.168.0.3", "path": "/"}}],
            "monitoring": {
                "logs": {"blobStorage": {"bucket": "job-logs"}},
                "metrics": {"blobStorage": {"bucket": "job-metrics"}},
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
                "metrics": {"blobStorage": {"bucket": "job-metrics"}},
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
                "ingressPublicIPs": ["192.168.0.3"],
                "standardStorageClassName": "standard",
                "nodePorts": {"kubelet": 10250, "http": 30080, "https": 30443},
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
    resource_pool_type_factory: Callable[[str], Dict[str, Any]],
    resource_preset_factory: Callable[[], Dict[str, Any]],
) -> PlatformConfig:
    return PlatformConfig(
        auth_url=URL("https://dev.neu.ro"),
        ingress_auth_url=URL("https://platformingressauth"),
        config_url=URL("https://dev.neu.ro"),
        api_url=URL("https://dev.neu.ro"),
        token="token",
        cluster_name=cluster_name,
        cloud_provider="gcp",
        namespace="platform",
        service_account_name="default",
        docker_config_secret_create=True,
        docker_config_secret_name="platform-docker-config",
        image_pull_secret_names=["platform-docker-config"],
        pre_pull_images=["neuromation/base"],
        standard_storage_class_name="platform-standard-topology-aware",
        kubernetes_version="1.14.9",
        kubernetes_node_labels=LabelsConfig(
            job="platform.neuromation.io/job",
            node_pool="platform.neuromation.io/nodepool",
            accelerator="platform.neuromation.io/accelerator",
            preemptible="platform.neuromation.io/preemptible",
        ),
        dns_name=f"{cluster_name}.org.neu.ro",
        jobs_namespace_create=True,
        jobs_namespace="platform-jobs",
        jobs_node_pools=[
            {"name": "n1-highmem-8-name", "idleSize": 0, "cpu": 1.0, "gpu": 1}
        ],
        jobs_resource_pool_types=[resource_pool_type_factory("192.168.0.0/16")],
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
        ingress_url=URL(f"https://{cluster_name}.org.neu.ro"),
        ingress_registry_url=URL(f"https://registry.{cluster_name}.org.neu.ro"),
        ingress_metrics_url=URL(f"https://metrics.{cluster_name}.org.neu.ro"),
        ingress_acme_environment="staging",
        ingress_controller_install=True,
        ingress_public_ips=[],
        ingress_cors_origins=[
            "https://release--neuro-web.netlify.app",
            "https://app.neu.ro",
        ],
        disks_storage_limit_per_user_gb=10240,
        disks_storage_class_name="platform-disk",
        service_traefik_name="platform-traefik",
        monitoring_logs_bucket_name="job-logs",
        monitoring_metrics_bucket_name="job-metrics",
        storages=[
            StorageConfig(
                type=StorageType.NFS,
                nfs_server="192.168.0.3",
                nfs_export_path="/",
            )
        ],
        helm_repo=HelmRepo(
            name=HelmRepoName.NEURO,
            url=URL("https://neuro.jfrog.io/neuro/helm-virtual-public"),
            username=cluster_name,
            password="password",
        ),
        docker_registry=DockerRegistry(
            url=URL("https://neuro.io"),
            email=f"{cluster_name}@neuromation.io",
            username=cluster_name,
            password="password",
        ),
        grafana_username="admin",
        grafana_password="grafana_password",
        consul_url=URL("http://consul:8500"),
        consul_install=False,
        sentry_dsn=URL("https://sentry"),
        sentry_sample_rate=0.1,
        gcp=GcpConfig(
            project="project",
            region="us-central1",
            service_account_key="{}",
            service_account_key_base64="e30=",
        ),
        docker_hub_config_secret_name="platform-docker-hub-config",
        docker_hub_registry=DockerRegistry(
            url=URL("https://index.docker.io/v1/"),
            email=f"{cluster_name}@neuromation.io",
            username=cluster_name,
            password="password",
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
            {"name": "p2.xlarge-name", "idleSize": 0, "cpu": 1.0, "gpu": 1}
        ],
        jobs_resource_pool_types=[resource_pool_type_factory()],
        aws=AwsConfig(
            region="us-east-1",
            registry_url=URL("https://platform.dkr.ecr.us-east-1.amazonaws.com"),
            s3_role_arn="",
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
            {"name": "Standard_NC6-name", "idleSize": 0, "cpu": 1.0, "gpu": 1}
        ],
        jobs_resource_pool_types=[resource_pool_type_factory()],
        storages=[
            StorageConfig(
                type=StorageType.AZURE_fILE,
                azure_storage_account_name="accountName1",
                azure_storage_account_key="accountKey1",
                azure_share_name="share",
            )
        ],
        azure=AzureConfig(
            region="westus",
            registry_url=URL("https://platform.azurecr.io"),
            registry_username="admin",
            registry_password="admin-password",
            blob_storage_account_name="accountName2",
            blob_storage_account_key="accountKey2",
        ),
    )


@pytest.fixture
def on_prem_platform_config(
    gcp_platform_config: PlatformConfig,
    resource_pool_type_factory: Callable[[], Dict[str, Any]],
    cluster_name: str,
) -> PlatformConfig:
    return replace(
        gcp_platform_config,
        gcp=None,
        ingress_public_ips=[IPv4Address("192.168.0.3")],
        standard_storage_class_name="standard",
        cloud_provider="on_prem",
        jobs_node_pools=[{"name": "gpu-name", "idleSize": 0, "cpu": 1.0, "gpu": 1}],
        jobs_resource_pool_types=[resource_pool_type_factory()],
        monitoring_metrics_bucket_name="",
        monitoring_metrics_storage_class_name="metrics-standard",
        monitoring_metrics_storage_size="100Gi",
        disks_storage_class_name="openebs-cstor",
        storages=[
            StorageConfig(
                type=StorageType.KUBERNETES,
                storage_size="1000Gi",
                storage_class_name="storage-standard",
            )
        ],
        on_prem=OnPremConfig(
            docker_registry_install=True,
            registry_url=URL("http://platform-docker-registry:5000"),
            registry_username="",
            registry_password="",
            registry_storage_class_name="registry-standard",
            registry_storage_size="100Gi",
            minio_install=True,
            blob_storage_public_url=URL(f"https://blob.{cluster_name}.org.neu.ro"),
            blob_storage_url=URL("http://platform-minio:9000"),
            blob_storage_region="minio",
            blob_storage_access_key="username",
            blob_storage_secret_key="password",
            blob_storage_class_name="blob-storage-standard",
            blob_storage_size="10Gi",
            kubelet_port=10250,
            http_node_port=30080,
            https_node_port=30443,
        ),
    )


@pytest.fixture
def on_prem_platform_config_with_emc_ecs(
    on_prem_platform_config: PlatformConfig,
    resource_pool_type_factory: Callable[[], Dict[str, Any]],
    cluster_name: str,
) -> PlatformConfig:
    return replace(
        on_prem_platform_config,
        emc_ecs_credentials=EMCECSCredentials(
            access_key_id="access-key",
            secret_access_key="secret-key",
            s3_endpoint=URL("https://emc-ecs.s3"),
            management_endpoint=URL("https://emc-ecs.management"),
            s3_assumable_role="s3-role",
        ),
    )


@pytest.fixture
def on_prem_platform_config_with_open_stack(
    on_prem_platform_config: PlatformConfig,
    resource_pool_type_factory: Callable[[], Dict[str, Any]],
    cluster_name: str,
) -> PlatformConfig:
    return replace(
        on_prem_platform_config,
        open_stack_credentials=OpenStackCredentials(
            account_id="account_id",
            password="password",
            s3_endpoint=URL("https://os.s3"),
            endpoint=URL("https://os.management"),
            region_name="region",
        ),
    )


@pytest.fixture
def vcd_platform_config(on_prem_platform_config: PlatformConfig) -> PlatformConfig:
    return replace(on_prem_platform_config, cloud_provider="vcd_mts")
