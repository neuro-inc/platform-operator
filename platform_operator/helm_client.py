import asyncio
import json
import logging
import shlex
from asyncio import subprocess
from typing import Any, Dict, List, Optional

import yaml

from .models import HelmRepo


logger = logging.getLogger(__name__)


class HelmException(Exception):
    pass


class HelmOptions:
    def __init__(self, **kwargs: Any) -> None:
        options: List[str] = []
        for key, value in kwargs.items():
            option_name = "--" + key.replace("_", "-")
            if isinstance(value, bool):
                if value:
                    options.append(option_name)
            elif value is not None:
                options.extend((option_name, shlex.quote(value)))
        self._options_dict = dict(**kwargs)
        self._options_str = " ".join(options)
        self._options_str_masked = " ".join(options)

    def add(self, **kwargs: Any) -> "HelmOptions":
        new_options = dict(**self._options_dict)
        new_options.update(**kwargs)
        return HelmOptions(**new_options)

    @property
    def masked(self) -> "HelmOptions":
        if "password" not in self._options_dict:
            return self
        new_options = dict(**self._options_dict)
        new_options["password"] = "*****"
        return HelmOptions(**new_options)

    def __str__(self) -> str:
        return self._options_str


class HelmClient:
    def __init__(self, kube_context: str = "", tiller_namespace: str = "",) -> None:
        self._global_options = HelmOptions(
            kube_context=kube_context or None, tiller_namespace=tiller_namespace or None
        )

    async def init(
        self, client_only: bool = False, wait: bool = False, skip_refresh: bool = False
    ) -> None:
        options = self._global_options.add(
            client_only=client_only, wait=wait, skip_refresh=skip_refresh
        )
        cmd = f"helm init {options!s}"
        logger.info("Running %s", cmd)
        process = await asyncio.create_subprocess_shell(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            stderr_text = (stderr or b"").decode().strip()
            logger.error("Failed to initialize helm: %s", stderr_text)
            raise HelmException("Failed to initialize helm")
        logger.info("Initialized helm")

    async def add_repo(self, repo: HelmRepo) -> None:
        options = self._global_options.add(
            username=repo.username or None, password=repo.password or None
        )
        logger.info(
            "Running helm repo add %s %s %s", repo.name, repo.url, options.masked,
        )
        process = await asyncio.create_subprocess_shell(
            f"helm repo add {repo.name} {repo.url!s} {options!s}",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            stderr_text = (stderr or b"").decode().strip()
            logger.error(
                "Failed to add helm repo %s %s: %s", repo.name, repo.url, stderr_text,
            )
            raise HelmException(f"Failed to add helm repo {repo.name} {repo.url!s}")
        logger.info("Added helm repo %s %s", repo.name, repo.url)

    async def update_repo(self) -> None:
        cmd = f"helm repo update {self._global_options!s}"
        logger.info("Running %s", cmd)
        process = await asyncio.create_subprocess_shell(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            stderr_text = (stderr or b"").decode().strip()
            logger.error(
                "Failed to update helm repositories: %s", stderr_text,
            )
            raise HelmException("Failed to update helm repositories")
        logger.info("Updated helm repo")

    async def get_release(self, release_name: str) -> Optional[Dict[str, Any]]:
        options = self._global_options.add(all=True, output="json")
        cmd = f'helm list "^{release_name}$" {options!s}'
        logger.info("Running %s", cmd)
        process = await asyncio.create_subprocess_shell(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            stderr_text = (stderr or b"").decode().strip()
            logger.error("Failed to initialize helm: %s", stderr_text)
            raise HelmException("Failed to initialize helm")
        stdout_text = stdout.decode()
        if not stdout_text:
            logger.info("Received empty response")
            return None
        logger.info("Received response %s", stdout_text)
        response_json = json.loads(stdout.decode())
        releases = response_json.get("Releases")
        return releases[0] if releases else None

    async def upgrade(
        self,
        release_name: str,
        chart_name: str,
        *,
        version: str = "",
        values: Optional[Dict[str, Any]] = None,
        namespace: Optional[str] = None,
        install: bool = False,
        wait: bool = False,
        timeout: Optional[int] = None,
    ) -> None:
        options = self._global_options.add(
            version=version,
            values="-",
            namespace=namespace,
            install=install,
            wait=wait,
            timeout=timeout,
        )
        logger.info(
            "Running helm upgrade %s %s %s", release_name, chart_name, options.masked,
        )
        process = await asyncio.create_subprocess_shell(
            f"helm upgrade {release_name} {chart_name} {options!s}",
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        values_yaml = yaml.safe_dump(values or {}).encode("utf-8")
        _, stderr = await process.communicate(values_yaml)
        if process.returncode != 0:
            stderr_text = (stderr or b"").decode().strip()
            logger.error(
                "Failed to upgrade helm release %s: %s", release_name, stderr_text
            )
            raise HelmException(f"Failed to upgrade release {release_name}")
        logger.info("Upgraded helm release %s", release_name)

    async def delete(self, release_name: str, *, purge: bool = False) -> None:
        options = self._global_options.add(purge=purge)
        cmd = f"helm delete {release_name} {options!s}"
        logger.info("Running %s", cmd)
        process = await asyncio.create_subprocess_shell(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        _, stderr = await process.communicate()
        stderr_text = (stderr or b"").decode().strip()
        if process.returncode != 0 and "not found" not in stderr_text:
            logger.error(
                "Failed to delete helm release %s: %s", release_name, stderr_text
            )
            raise HelmException(f"Failed to delete release {release_name}")
        logger.info("Deleted helm release %s", release_name)
