from __future__ import annotations

import os
import threading
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import aiobotocore.session
import moto.server
import pytest
from werkzeug.serving import make_server
from yarl import URL

from platform_operator.aws_client import AwsElbClient


@dataclass(frozen=True)
class AppAddress:
    host: str
    port: int


class AppServer(threading.Thread):
    def __init__(self, app: Any, app_address: AppAddress):
        threading.Thread.__init__(self)
        self._server = make_server(
            host=app_address.host, port=app_address.port, app=app, threaded=False
        )

    def run(self) -> None:
        self._server.serve_forever()

    def shutdown(self) -> None:
        self._server.shutdown()


@contextmanager
def create_app_server(app: Any, port: int = 8080) -> Iterator[AppAddress]:
    app_address = AppAddress("0.0.0.0", port)
    app_server = AppServer(app, app_address)
    try:
        app_server.start()
        yield app_address
    finally:
        app_server.shutdown()


@pytest.fixture(scope="session")
def elb_endpoint_url() -> Iterator[URL]:
    app = moto.server.DomainDispatcherApplication(moto.server.create_backend_app)
    with create_app_server(app, port=5000) as api_address:
        yield URL(f"http://{api_address.host}:{api_address.port}")


@pytest.fixture(scope="session")
def ec2_endpoint_url() -> Iterator[URL]:
    app = moto.server.DomainDispatcherApplication(moto.server.create_backend_app)
    with create_app_server(app, port=5001) as api_address:
        yield URL(f"http://{api_address.host}:{api_address.port}")


@pytest.fixture(scope="session")
def aws_config() -> dict[str, str]:
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"

    return {
        "region": "us-east-1",
        "access_key_id": "testing",
        "secret_access_key": "testing",
    }


@pytest.fixture
async def elb_client(
    aws_config: dict[str, str], elb_endpoint_url: URL
) -> AsyncIterator[AwsElbClient]:
    async with AwsElbClient(
        region=aws_config["region"],
        access_key_id=aws_config["access_key_id"],
        secret_access_key=aws_config["secret_access_key"],
        endpoint_url=elb_endpoint_url,
    ) as client:
        yield client


@pytest.fixture
async def ec2_client(
    aws_config: dict[str, str], ec2_endpoint_url: URL
) -> AsyncIterator[aiobotocore.session.AioBaseClient]:
    session = aiobotocore.session.get_session()
    async with session.create_client(
        "ec2",
        region_name=aws_config["region"],
        aws_access_key_id=aws_config["access_key_id"],
        aws_secret_access_key=aws_config["secret_access_key"],
        endpoint_url=str(ec2_endpoint_url),
    ) as client:
        yield client
