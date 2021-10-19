import asyncio
import enum
import json
import logging
import shlex
from asyncio import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .models import HelmRepo


logger = logging.getLogger(__name__)


class HelmException(Exception):
    pass


class ReleaseStatus(enum.Enum):
    UNKNOWN = "unknown"
    DEPLOYED = "deployed"
    UNINSTALLED = "uninstalled"
    SUPERSEDED = "superseded"
    FAILED = "failed"
    UNINSTALLING = "uninstalling"
    PENDINGINSTALL = "pending-install"
    PENDINGUPGRADE = "pending-upgrade"
    PENDINGROLLBACK = "pending-rollback"


@dataclass(frozen=True)
class Release:
    name: str
    namespace: str
    chart: str
    status: ReleaseStatus

    @classmethod
    def parse(cls, payload: Dict[str, Any]) -> "Release":
        return cls(
            name=payload["name"],
            namespace=payload["namespace"],
            chart=payload["chart"],
            status=ReleaseStatus(payload["status"]),
        )


class HelmOptions:
    def __init__(self, **kwargs: Any) -> None:
        self._options_dict: Dict[str, Any] = {}
        options: List[str] = []
        for key, value in kwargs.items():
            if value is None:
                continue
            self._options_dict[key] = value
            option_name = "--" + key.replace("_", "-")
            if isinstance(value, bool):
                if value:
                    options.append(option_name)
            else:
                options.extend((option_name, shlex.quote(str(value))))
        self._options_str = " ".join(options)

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
    def __init__(self, kube_context: str = "", namespace: str = "") -> None:
        self._global_options = HelmOptions(
            kube_context=kube_context or None, namespace=namespace or None
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
        cmd = f"helm repo add {repo.name} {repo.url!s} {options!s} --force-update"
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

    async def get_release(self, release_name: str) -> Optional[Release]:
        options = self._global_options.add(filter=f"^{release_name}$", output="json")
        cmd = f"helm list {options!s}"
        logger.info("Running %s", cmd)
        process, stdout_text, stderr_text = await self._run(
            cmd, capture_stdout=True, capture_stderr=True
        )
        if process.returncode != 0:
            logger.error("Failed to list releases: %s", stderr_text.strip())
            raise HelmException("Failed to list releases")
        if not stdout_text:
            logger.info("Received empty response")
            return None
        logger.debug("Received response %s", stdout_text)
        releases = json.loads(stdout_text)
        return Release.parse(releases[0]) if releases else None

    async def get_release_values(self, release_name: str) -> Optional[Dict[str, Any]]:
        options = self._global_options.add(output="json")
        cmd = f"helm get values {release_name} {options!s}"
        logger.info("Running %s", cmd)
        process, stdout_text, stderr_text = await self._run(
            cmd,
            capture_stdout=True,
            capture_stderr=True,
        )
        if process.returncode != 0:
            if "not found" in stdout_text:
                logger.info("Release %s not found", release_name)
                return None
            logger.error("Failed to get values: %s", stderr_text.strip())
            raise HelmException("Failed to get values")
        logger.debug("Received response %s", stdout_text)
        return json.loads(stdout_text)

    async def upgrade(
        self,
        release_name: str,
        chart_name: str,
        *,
        version: str = "",
        values: Optional[Dict[str, Any]] = None,
        install: bool = False,
        wait: bool = False,
        timeout: Optional[int] = None,
    ) -> None:
        options = self._global_options.add(
            version=version,
            values="-",
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

    async def delete(self, release_name: str) -> None:
        options = self._global_options
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
