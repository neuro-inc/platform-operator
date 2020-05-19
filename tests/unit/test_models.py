from pathlib import Path
from typing import Any, Dict

import pytest
from yarl import URL

from platform_operator.models import (
    Cluster,
    Config,
    HelmChartNames,
    HelmChartVersions,
    HelmReleaseNames,
    HelmRepo,
    KubeClientAuthType,
    KubeConfig,
    PlatformConfig,
)


class TestConfig:
    def test_config(self) -> None:
        env = {
            "NP_PLATFORM_URL": "https://dev.neu.ro",
            "NP_CONTROLLER_LOG_LEVEL": "debug",
            "NP_CONTROLLER_RETRIES": "5",
            "NP_CONTROLLER_BACKOFF": "120",
            "NP_KUBE_URL": "https://kubernetes.default",
            "NP_KUBE_CERT_AUTHORITY_PATH": "/ca.crt",
            "NP_KUBE_CERT_AUTHORITY_DATA_PEM": "cert-authority-data",
            "NP_KUBE_AUTH_TYPE": "certificate",
            "NP_KUBE_AUTH_CERT_PATH": "/client.crt",
            "NP_KUBE_AUTH_CERT_KEY_PATH": "/client.key",
            "NP_KUBE_AUTH_TOKEN_PATH": "/token",
            "NP_KUBE_AUTH_TOKEN": "token",
            "NP_HELM_STABLE_REPO_URL": (
                "https://kubernetes-charts.storage.googleapis.com"
            ),
            "NP_HELM_SERVICE_ACCOUNT_NAME": "default",
            "NP_HELM_PLATFORM_CHART_VERSION": "1.0.0",
            "NP_HELM_OBS_CSI_DRIVER_CHART_VERSION": "2.0.0",
            "NP_HELM_NFS_SERVER_CHART_VERSION": "3.0.0",
            "NP_PLATFORM_NAMESPACE": "platform",
            "NP_PLATFORM_JOBS_NAMESPACE": "platform-jobs",
        }
        assert Config.load_from_env(env) == Config(
            log_level="DEBUG",
            retries=5,
            backoff=120,
            kube_config=KubeConfig(
                url=URL("https://kubernetes.default"),
                cert_authority_path=Path("/ca.crt"),
                cert_authority_data_pem="cert-authority-data",
                auth_type=KubeClientAuthType.CERTIFICATE,
                auth_cert_path=Path("/client.crt"),
                auth_cert_key_path=Path("/client.key"),
                auth_token_path=Path("/token"),
                auth_token="token",
                conn_timeout_s=300,
                read_timeout_s=100,
                conn_pool_size=100,
            ),
            helm_stable_repo=HelmRepo(
                name="stable",
                url=URL("https://kubernetes-charts.storage.googleapis.com"),
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

    def test_config_defaults(self) -> None:
        env = {
            "NP_PLATFORM_URL": "https://dev.neu.ro",
            "NP_KUBE_URL": "https://kubernetes.default",
            "NP_KUBE_AUTH_TYPE": "none",
            "NP_HELM_STABLE_REPO_URL": (
                "https://kubernetes-charts.storage.googleapis.com"
            ),
            "NP_HELM_SERVICE_ACCOUNT_NAME": "default",
            "NP_HELM_PLATFORM_CHART_VERSION": "1.0.0",
            "NP_HELM_OBS_CSI_DRIVER_CHART_VERSION": "2.0.0",
            "NP_HELM_NFS_SERVER_CHART_VERSION": "3.0.0",
            "NP_PLATFORM_NAMESPACE": "platform",
            "NP_PLATFORM_JOBS_NAMESPACE": "platform-jobs",
        }
        assert Config.load_from_env(env) == Config(
            log_level="INFO",
            retries=3,
            backoff=60,
            kube_config=KubeConfig(
                url=URL("https://kubernetes.default"),
                auth_type=KubeClientAuthType.NONE,
                conn_timeout_s=300,
                read_timeout_s=100,
                conn_pool_size=100,
            ),
            helm_stable_repo=HelmRepo(
                name="stable",
                url=URL("https://kubernetes-charts.storage.googleapis.com"),
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


class TestCluster:
    def test_name(self) -> None:
        cluster = Cluster({"name": "test"})

        assert cluster.name == "test"

    def test_cloud_provider_type(self) -> None:
        cluster = Cluster({"cloud_provider": {"type": "gcp"}})

        assert cluster.cloud_provider_type == "gcp"

    def test_acme_environment(self) -> None:
        cluster = Cluster({"lb": {"acme_environment": "staging"}})

        assert cluster.acme_environment == "staging"

        cluster = Cluster({"lb": {"http": {"acme_environment": "staging"}}})

        assert cluster.acme_environment == "staging"

    def test_dns_zone_name(self) -> None:
        cluster = Cluster({"dns": {"zone_name": "test.org.neu.ro."}})

        assert cluster.dns_zone_name == "test.org.neu.ro."


class TestPlatformConfig:
    @pytest.fixture
    def traefik_service(self) -> Dict[str, Any]:
        return {
            "metadata": {"name", "platform-traefik"},
            "status": {"loadBalancer": {"ingress": [{"ip": "192.168.0.1"}]}},
        }

    @pytest.fixture
    def ssh_auth_service(self) -> Dict[str, Any]:
        return {
            "metadata": {"name", "ssh-auth"},
            "status": {"loadBalancer": {"ingress": [{"ip": "192.168.0.2"}]}},
        }

    @pytest.fixture
    def aws_traefik_service(self) -> Dict[str, Any]:
        return {
            "metadata": {"name", "platform-traefik"},
            "status": {"loadBalancer": {"ingress": [{"hostname": "traefik"}]}},
        }

    @pytest.fixture
    def aws_ssh_auth_service(self) -> Dict[str, Any]:
        return {
            "metadata": {"name", "ssh-auth"},
            "status": {"loadBalancer": {"ingress": [{"hostname": "ssh-auth"}]}},
        }

    @pytest.fixture
    def aws_traefik_lb(self) -> Dict[str, Any]:
        return {
            "CanonicalHostedZoneNameID": "/hostedzone/traefik",
        }

    @pytest.fixture
    def aws_ssh_auth_lb(self) -> Dict[str, Any]:
        return {
            "CanonicalHostedZoneNameID": "/hostedzone/ssh-auth",
        }

    @pytest.fixture
    def service_account_secret(self) -> Dict[str, Any]:
        return {"data": {"ca.crt": "cert-authority-data", "token": "token"}}

    def test_create_dns_config(
        self,
        gcp_platform_config: PlatformConfig,
        traefik_service: Dict[str, Any],
        ssh_auth_service: Dict[str, Any],
    ) -> None:
        result = gcp_platform_config.create_dns_config(
            traefik_service=traefik_service, ssh_auth_service=ssh_auth_service,
        )
        zone_name = gcp_platform_config.dns_zone_name

        assert result == {
            "zone_id": gcp_platform_config.dns_zone_id,
            "zone_name": gcp_platform_config.dns_zone_name,
            "name_servers": gcp_platform_config.dns_zone_name_servers,
            "a_records": [
                {"name": zone_name, "ips": ["192.168.0.1"]},
                {"name": f"*.jobs.{zone_name}", "ips": ["192.168.0.1"]},
                {"name": f"registry.{zone_name}", "ips": ["192.168.0.1"]},
                {"name": f"ssh-auth.{zone_name}", "ips": ["192.168.0.2"]},
            ],
        }

    def test_create_on_prem_dns_config(
        self,
        on_prem_platform_config: PlatformConfig,
        traefik_service: Dict[str, Any],
        ssh_auth_service: Dict[str, Any],
    ) -> None:
        result = on_prem_platform_config.create_dns_config(
            traefik_service=traefik_service, ssh_auth_service=ssh_auth_service,
        )
        zone_name = on_prem_platform_config.dns_zone_name

        assert result == {
            "zone_id": on_prem_platform_config.dns_zone_id,
            "zone_name": on_prem_platform_config.dns_zone_name,
            "name_servers": on_prem_platform_config.dns_zone_name_servers,
            "a_records": [
                {"name": zone_name, "ips": ["192.168.0.3"]},
                {"name": f"*.jobs.{zone_name}", "ips": ["192.168.0.3"]},
                {"name": f"registry.{zone_name}", "ips": ["192.168.0.3"]},
                {"name": f"ssh-auth.{zone_name}", "ips": ["192.168.0.3"]},
            ],
        }

    def test_create_aws_dns_config(
        self,
        aws_platform_config: PlatformConfig,
        aws_traefik_service: Dict[str, Any],
        aws_ssh_auth_service: Dict[str, Any],
        aws_traefik_lb: Dict[str, Any],
        aws_ssh_auth_lb: Dict[str, Any],
    ) -> None:
        result = aws_platform_config.create_dns_config(
            traefik_service=aws_traefik_service,
            ssh_auth_service=aws_ssh_auth_service,
            aws_traefik_lb=aws_traefik_lb,
            aws_ssh_auth_lb=aws_ssh_auth_lb,
        )
        zone_name = aws_platform_config.dns_zone_name

        assert result == {
            "zone_id": aws_platform_config.dns_zone_id,
            "zone_name": aws_platform_config.dns_zone_name,
            "name_servers": aws_platform_config.dns_zone_name_servers,
            "a_records": [
                {
                    "name": zone_name,
                    "dns_name": "traefik",
                    "zone_id": "/hostedzone/traefik",
                },
                {
                    "name": f"*.jobs.{zone_name}",
                    "dns_name": "traefik",
                    "zone_id": "/hostedzone/traefik",
                },
                {
                    "name": f"registry.{zone_name}",
                    "dns_name": "traefik",
                    "zone_id": "/hostedzone/traefik",
                },
                {
                    "name": f"ssh-auth.{zone_name}",
                    "dns_name": "ssh-auth",
                    "zone_id": "/hostedzone/ssh-auth",
                },
            ],
        }
