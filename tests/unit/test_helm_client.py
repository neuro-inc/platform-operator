from platform_operator.helm_client import HelmOptions


class TestHelmOptions:
    def test_str(self) -> None:
        options = HelmOptions(
            wait=False,
            namespace="default",
            timeout="600s",
        )

        assert str(options) == "--namespace default --timeout 600s"

    def test_str_empty(self) -> None:
        assert str(HelmOptions()) == ""

    def test_add(self) -> None:
        options = HelmOptions().add(namespace="default")

        assert str(options) == "--namespace default"

    def test_mask_password(self) -> None:
        options = HelmOptions(username="user", password="qwerty78")

        assert str(options.masked) == "--username user --password '*****'"

    def test_mask_empty_password(self) -> None:
        options = HelmOptions(username=None, password=None)

        assert str(options.masked) == ""
