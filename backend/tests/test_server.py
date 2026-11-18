from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

import httpx
import pytest


SENSITIVE_VALUE = "server-regression-test-secret"
SERVER_SOURCE = '''
import os

from starlette.background import BackgroundTask
from starlette.responses import JSONResponse, StreamingResponse

from app.main import create_app

app = create_app()


def fail():
    raise RuntimeError(os.environ["AI_DEFAULT_MODEL_API_KEY"])


@app.get("/api/test-error")
async def error():
    fail()


@app.get("/api/test-chained-error")
async def chained_error():
    try:
        fail()
    except RuntimeError as exc:
        raise ValueError("Public error message") from exc


@app.get("/api/test-stream-error")
async def stream_error():
    async def chunks():
        yield b"first chunk\\n"
        fail()
    return StreamingResponse(chunks(), media_type="text/plain")


@app.get("/api/test-background-error")
async def background_error():
    return JSONResponse({"accepted": True}, background=BackgroundTask(fail))
'''


@pytest.fixture
def running_server(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_DEFAULT_MODEL_API_KEY", SENSITIVE_VALUE)
    (tmp_path / "regression_server.py").write_text(SERVER_SOURCE, encoding="utf-8")

    @contextmanager
    def start(log_level="info"):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        log_path = tmp_path / "server.log"
        child_env = dict(os.environ)
        child_env["PYTHONIOENCODING"] = "utf-8"
        with log_path.open("w", encoding="utf-8") as log_file:
            process = subprocess.Popen(
                [
                    sys.executable, "-m", "uvicorn", "regression_server:app",
                    "--host", "127.0.0.1", "--port", str(port),
                    "--log-level", log_level,
                ],
                cwd=tmp_path,
                env=child_env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                with httpx.Client(
                    base_url=f"http://127.0.0.1:{port}", timeout=3, trust_env=False
                ) as client:
                    deadline = time.monotonic() + 10
                    while True:
                        if process.poll() is not None:
                            pytest.fail("Regression server exited before startup")
                        try:
                            response = client.get("/api/health")
                            assert response.status_code == 200
                            break
                        except httpx.TransportError:
                            if time.monotonic() >= deadline:
                                pytest.fail("Regression server startup timed out")
                            time.sleep(0.05)
                    yield client, log_path
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

    return start


@pytest.mark.parametrize("log_level", ["info", "debug"])
@pytest.mark.parametrize("path", ["/api/test-error", "/api/test-chained-error"])
def test_uvicorn_does_not_log_sensitive_exceptions(running_server, log_level, path):
    with running_server(log_level) as (client, log_path):
        response = client.get(path, headers={"Accept": "text/html"})
        assert response.status_code == 500
        assert response.json() == {
            "error": {"code": "internal_error", "message": "Internal server error."}
        }
        assert SENSITIVE_VALUE not in response.text
        assert client.get("/api/health").status_code == 200

    output = log_path.read_text(encoding="utf-8")
    assert "Unhandled server error" in output
    assert SENSITIVE_VALUE not in output
    assert "Traceback" not in output


def test_stream_failure_aborts_response_without_logging_sensitive_exception(running_server):
    with running_server("debug") as (client, log_path):
        with client.stream("GET", "/api/test-stream-error") as response:
            assert response.status_code == 200
            with pytest.raises(httpx.RemoteProtocolError):
                response.read()
        assert client.get("/api/health").status_code == 200

    output = log_path.read_text(encoding="utf-8")
    assert "Unhandled server error" in output
    assert SENSITIVE_VALUE not in output


def test_background_failure_preserves_completed_response_and_safe_logs(running_server):
    with running_server("debug") as (client, log_path):
        response = client.get("/api/test-background-error")
        assert response.status_code == 200
        assert response.json() == {"accepted": True}
        assert client.get("/api/health").status_code == 200

    output = log_path.read_text(encoding="utf-8")
    assert "Unhandled server error" in output
    assert SENSITIVE_VALUE not in output
    assert "Traceback" not in output


def test_cli_test_ignores_working_copy_dotenv(tmp_path):
    """Run the actual CLI test in a copy containing a deliberately unreadable .env."""
    copied_tests = tmp_path / "working-copy" / "tests"
    copied_tests.mkdir(parents=True)
    source_tests = Path(__file__).resolve().parent
    for name in ("test_http.py", "conftest.py"):
        shutil.copyfile(source_tests / name, copied_tests / name)
    (copied_tests.parent / ".env").write_bytes(b"\xffinvalid-utf8")
    child_env = dict(os.environ)
    child_env.pop("PYTEST_ADDOPTS", None)
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
            "--basetemp", str(tmp_path / "isolated-tests"),
            str(copied_tests / "test_http.py")
            + "::test_invalid_configuration_cli_exits_without_sensitive_output",
        ],
        cwd=copied_tests.parent,
        env=child_env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
