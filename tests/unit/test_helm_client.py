from platform_operator.helm_client import HelmOptions


class TestHelmOptions:
    def test_str(self) -> None:
        options = HelmOptions(
            client_only=True,
            wait=False,
            tiller_namespace="default",
            namespace=None,
            timeout=600,
        )

        assert str(options) == "--client-only --tiller-namespace default --timeout 600"

    def test_str_empty(self) -> None:
        assert str(HelmOptions()) == ""

    def test_add(self) -> None:
        options = HelmOptions().add(client_only=True)

        assert str(options) == "--client-only"

    def test_mask_password(self) -> None:
        options = HelmOptions(username="user", password="qwerty78")

        assert str(options.masked) == "--username user --password '*****'"

    def test_mask_empty_password(self) -> None:
        options = HelmOptions(username=None, password=None)

        assert str(options.masked) == ""
