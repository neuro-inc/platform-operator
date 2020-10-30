import asyncio
import json
import logging
import shlex
from asyncio import subprocess
from typing import Any, Dict, List, Optional, Tuple

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
                options.extend((option_name, shlex.quote(str(value))))
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
    def __init__(
        self,
        kube_context: str = "",
        tiller_namespace: str = "",
    ) -> None:
        self._global_options = HelmOptions(
            kube_context=kube_context or None, tiller_namespace=tiller_namespace or None
        )

    async def _run(
        self,
        cmd: str,
        input_text: str = "",
        capture_stdout: bool = False,
        capture_stderr: bool = False,
    ) -> Tuple[subprocess.Process, str, str]:
        input_bytes = input_text.encode("utf-8")
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdin=subprocess.PIPE if input_bytes else None,
            stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
            stderr=subprocess.PIPE if capture_stderr else subprocess.DEVNULL,
        )
        stdout, stderr = await process.communicate(input_bytes or None)
        stdout_text = (stdout or b"").decode("utf-8")
        stderr_text = (stderr or b"").decode("utf-8")
        return (process, stdout_text, stderr_text)

    async def init(
        self, client_only: bool = False, wait: bool = False, skip_refresh: bool = False
    ) -> None:
        options = self._global_options.add(
            client_only=client_only, wait=wait, skip_refresh=skip_refresh
        )
        cmd = f"helm init {options!s}"
        logger.info("Running %s", cmd)
        process, _, stderr_text = await self._run(
            cmd, capture_stdout=False, capture_stderr=True
        )
        if process.returncode != 0:
            logger.error("Failed to initialize helm: %s", stderr_text.strip())
            raise HelmException("Failed to initialize helm")
        logger.info("Initialized helm")

    async def add_repo(self, repo: HelmRepo) -> None:
        options = self._global_options.add(
            username=repo.username or None, password=repo.password or None
        )
        logger.info(
            "Running helm repo add %s %s %s",
            repo.name,
            repo.url,
            options.masked,
        )
        cmd = f"helm repo add {repo.name} {repo.url!s} {options!s}"
        process, _, stderr_text = await self._run(
            cmd,
            capture_stdout=False,
            capture_stderr=True,
        )
        if process.returncode != 0:
            logger.error(
                "Failed to add helm repo %s %s: %s",
                repo.name,
                repo.url,
                stderr_text.strip(),
            )
            raise HelmException(f"Failed to add helm repo {repo.name} {repo.url!s}")
        logger.info("Added helm repo %s %s", repo.name, repo.url)

    async def update_repo(self) -> None:
        cmd = f"helm repo update {self._global_options!s}"
        logger.info("Running %s", cmd)
        process, _, stderr_text = await self._run(
            cmd,
            capture_stdout=False,
            capture_stderr=True,
        )
        if process.returncode != 0:
            logger.error(
                "Failed to update helm repositories: %s",
                stderr_text.strip(),
            )
            raise HelmException("Failed to update helm repositories")
        logger.info("Updated helm repo")

    async def get_release(self, release_name: str) -> Optional[Dict[str, Any]]:
        options = self._global_options.add(all=True, output="json")
        cmd = f'helm list "^{release_name}$" {options!s}'
        logger.info("Running %s", cmd)
        process, stdout_text, stderr_text = await self._run(
            cmd,
            capture_stdout=True,
            capture_stderr=True,
        )
        if process.returncode != 0:
            logger.error("Failed to initialize helm: %s", stderr_text.strip())
            raise HelmException("Failed to initialize helm")
        if not stdout_text:
            logger.info("Received empty response")
            return None
        logger.info("Received response %s", stdout_text)
        response_json = json.loads(stdout_text)
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
            "Running helm upgrade %s %s %s",
            release_name,
            chart_name,
            options.masked,
        )
        cmd = f"helm upgrade {release_name} {chart_name} {options!s}"
        values_yaml = yaml.safe_dump(values or {})
        process, _, stderr_text = await self._run(
            cmd,
            values_yaml,
            capture_stdout=False,
            capture_stderr=True,
        )
        if process.returncode != 0:
            logger.error(
                "Failed to upgrade helm release %s: %s",
                release_name,
                stderr_text.strip(),
            )
            raise HelmException(f"Failed to upgrade release {release_name}")
        logger.info("Upgraded helm release %s", release_name)

    async def delete(self, release_name: str, *, purge: bool = False) -> None:
        options = self._global_options.add(purge=purge)
        cmd = f"helm delete {release_name} {options!s}"
        logger.info("Running %s", cmd)
        process, _, stderr_text = await self._run(
            cmd,
            capture_stdout=False,
            capture_stderr=True,
        )
        if process.returncode != 0 and "not found" not in stderr_text:
            logger.error(
                "Failed to delete helm release %s: %s",
                release_name,
                stderr_text.strip(),
            )
            raise HelmException(f"Failed to delete release {release_name}")
        logger.info("Deleted helm release %s", release_name)
