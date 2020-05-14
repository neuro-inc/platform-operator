from pathlib import Path

from yarl import URL

from platform_operator.models import (
    Config,
    HelmChartNames,
    HelmChartVersions,
    HelmReleaseNames,
    HelmRepo,
    HelmRepoName,
    KubeClientAuthType,
    KubeConfig,
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
                platform="platform", openebs="openebs", obs_csi_driver="obs-csi-driver"
            ),
            helm_chart_names=HelmChartNames(),
            helm_chart_versions=HelmChartVersions(
                platform="1.0.0", obs_csi_driver="2.0.0", openebs="3.0.0",
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
                platform="platform", obs_csi_driver="platform-obs-csi-driver"
            ),
            helm_chart_names=HelmChartNames(),
            helm_chart_versions=HelmChartVersions(
                platform="1.0.0", obs_csi_driver="2.0.0"
            ),
            helm_service_account="default",
            platform_url=URL("https://dev.neu.ro"),
            platform_auth_url=URL("https://dev.neu.ro"),
            platform_api_url=URL("https://dev.neu.ro/api/v1"),
            platform_namespace="platform",
            platform_jobs_namespace="platform-jobs",
        )
