# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""Pytest fixtures for integration tests using testcontainers."""

from __future__ import annotations

import subprocess
import tempfile
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import docker
import pytest
import requests
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

from frequenz.client.marketmetering import MarketMeteringApiClient

if TYPE_CHECKING:
    from collections.abc import Generator

SERVICE_REPO_PATH = (
    Path(__file__).parent.parent.parent / "frequenz-service-marketmetering"
)
SCHEMA_PATH = SERVICE_REPO_PATH / "database" / "greptimedb" / "create_schema.sql"
SERVICE_BINARY = SERVICE_REPO_PATH / "target" / "release" / "marketmeteringd"

GREPTIMEDB_IMAGE = "greptime/greptimedb:v1.0.0-rc.2"
GREPTIMEDB_GRPC_PORT = 4001
GREPTIMEDB_HTTP_PORT = 4000

pytestmark = pytest.mark.integration


def _docker_available() -> bool:
    """Check if Docker is available and running."""
    try:
        client = docker.from_env()
        client.ping()
        return True
    except docker.errors.DockerException:
        return False


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "integration: integration tests requiring Docker"
    )


def pytest_collection_modifyitems(
    config: pytest.Config,  # pylint: disable=unused-argument
    items: list[pytest.Item],
) -> None:
    """Skip integration tests if Docker is not available."""
    if not _docker_available():
        skip_reason = pytest.mark.skip(reason="Docker not available")
        for item in items:
            if "integration" in [m.name for m in item.iter_markers()]:
                item.add_marker(skip_reason)


class _GreptimeDBContainer:
    """GreptimeDB testcontainer wrapper."""

    def __init__(self) -> None:
        self._container: DockerContainer = DockerContainer(GREPTIMEDB_IMAGE)
        self._container.with_exposed_ports(
            GREPTIMEDB_HTTP_PORT, GREPTIMEDB_GRPC_PORT, 4002, 4003
        )
        self._container.with_command(
            "standalone start --http-addr 0.0.0.0:4000 --rpc-bind-addr 0.0.0.0:4001 "
            "--mysql-addr 0.0.0.0:4002 --postgres-addr 0.0.0.0:4003"
        )

    def start(self) -> None:
        """Start the container."""
        self._container.start()

    def stop(self) -> None:
        """Stop the container."""
        self._container.stop()

    def get_grpc_endpoint(self) -> str:
        """Get the gRPC endpoint for GreptimeDB."""
        host = self._container.get_container_host_ip()
        port = self._container.get_exposed_port(GREPTIMEDB_GRPC_PORT)
        return f"http://{host}:{port}"

    def get_http_url(self) -> str:
        """Get the HTTP URL for GreptimeDB."""
        host = self._container.get_container_host_ip()
        port = self._container.get_exposed_port(GREPTIMEDB_HTTP_PORT)
        return f"http://{host}:{port}"

    def wait_for_health(self, timeout: int = 30) -> None:
        """Wait for GreptimeDB to be healthy."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = requests.get(f"{self.get_http_url()}/health", timeout=2)
                if resp.status_code == 200:
                    return
            except requests.RequestException:
                pass
            time.sleep(0.5)
        raise RuntimeError("GreptimeDB health check timed out")


@pytest.fixture(scope="session")
def greptimedb_container() -> Generator[_GreptimeDBContainer, None, None]:
    """Start a GreptimeDB container for the test session."""
    if not _docker_available():
        pytest.skip("Docker not available")

    container = _GreptimeDBContainer()
    container.start()
    # pylint: disable-next=protected-access
    wait_for_logs(container._container, predicate=".*server started.*", timeout=30)
    container.wait_for_health()
    yield container
    container.stop()


@pytest.fixture(scope="session")
def greptimedb_schema(
    greptimedb_container: _GreptimeDBContainer,
) -> str:
    """Initialize the GreptimeDB schema."""
    http_url = greptimedb_container.get_http_url()
    sql_path = SCHEMA_PATH

    if not sql_path.exists():
        pytest.skip(
            f"Schema file not found at {sql_path}. Is the service repo checked out?"
        )

    sql_content = sql_path.read_text()

    response = requests.post(
        f"{http_url}/v1/sql",
        data={"sql": sql_content},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Failed to initialize schema: {response.text}")

    return greptimedb_container.get_grpc_endpoint()


@pytest.fixture(scope="session")
def service_binary() -> Path:
    """Return path to the marketmeteringd binary."""
    if not SERVICE_BINARY.exists():
        pytest.skip(
            f"Service binary not found at {SERVICE_BINARY}. "
            "Build the service with 'cargo build --release'"
        )
    return SERVICE_BINARY


@pytest.fixture(scope="session")
def service_config(
    greptimedb_container: _GreptimeDBContainer,
    service_binary: Path,  # pylint: disable=unused-argument
) -> Path:
    """Create a config file for the marketmeteringd service."""
    greptimedb_endpoint = greptimedb_container.get_grpc_endpoint()

    config_content = f"""[net]
ip = "[::1]"
port = 50051

[auth]
enabled = false

[storage]
backend = "greptime"
endpoint = "{greptimedb_endpoint}/marketmetering"

[service]
upsert_stream_buf_size = 32
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".toml", delete=False
    ) as config_file:
        config_file.write(config_content)
        return Path(config_file.name)


@pytest.fixture(scope="session")
def service_process(
    service_binary: Path,
    service_config: Path,
) -> Generator[subprocess.Popen[Any], None, None]:
    """Start the marketmeteringd service."""
    # pylint: disable-next=consider-using-with
    proc = subprocess.Popen(
        [str(service_binary), "--config", str(service_config)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    time.sleep(2)

    if proc.poll() is not None:
        stdout, stderr = proc.communicate(timeout=5)
        raise RuntimeError(
            f"Service failed to start.\nstdout: {stdout.decode()}\nstderr: {stderr.decode()}"
        )

    yield proc

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
async def client(
    service_process: subprocess.Popen[Any],  # pylint: disable=unused-argument
) -> AsyncIterator[MarketMeteringApiClient]:
    """Create a client connected to the test service."""
    c = MarketMeteringApiClient(
        server_url="grpc://[::1]:50051?ssl=false",
        auth_key="",
    )
    yield c
