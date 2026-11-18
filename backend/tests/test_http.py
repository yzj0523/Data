import subprocess
import sys

import httpx
import pytest

from app.main import create_app

SENSITIVE_VALUE = "test-secret-must-not-be-exposed"
pytestmark = pytest.mark.anyio


def http_client(app=None, *, raise_app_exceptions=True):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=app if app is not None else create_app(),
            raise_app_exceptions=raise_app_exceptions,
        ),
        base_url="http://testserver",
    )


async def test_health_without_model_credentials():
    async with http_client() as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "environment": "development",
        "model": {"status": "not_configured"},
    }


async def test_complete_model_configuration_is_not_a_connection_test(monkeypatch):
    monkeypatch.setenv("AI_DEFAULT_MODEL_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("AI_DEFAULT_MODEL_NAME", "test-model")
    monkeypatch.setenv("AI_DEFAULT_MODEL_API_KEY", SENSITIVE_VALUE)
    monkeypatch.setenv("AI_ENVIRONMENT", "production")

    async with http_client() as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "environment": "production",
        "model": {"status": "not_checked"},
    }
    assert SENSITIVE_VALUE not in response.text
    assert "example.invalid" not in response.text


async def test_partial_model_configuration_does_not_prevent_startup(monkeypatch):
    monkeypatch.setenv("AI_DEFAULT_MODEL_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("AI_DEFAULT_MODEL_NAME", "test-model")
    monkeypatch.setenv("AI_DEFAULT_MODEL_API_KEY", "   ")

    async with http_client() as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["model"]["status"] == "not_configured"


async def test_dotenv_settings_and_environment_precedence(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "AI_ENVIRONMENT=test\n"
        "AI_DEFAULT_MODEL_BASE_URL=\n"
        "AI_DEFAULT_MODEL_NAME=\n"
        "AI_DEFAULT_MODEL_API_KEY=\n",
        encoding="utf-8",
    )
    async with http_client() as client:
        assert (await client.get("/api/health")).json()["environment"] == "test"

    monkeypatch.setenv("AI_ENVIRONMENT", "production")
    async with http_client() as client:
        assert (await client.get("/api/health")).json()["environment"] == "production"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("AI_ENVIRONMENT", SENSITIVE_VALUE),
        ("AI_HOST", SENSITIVE_VALUE),
        ("AI_PORT", SENSITIVE_VALUE),
        ("AI_PORT", "0"),
        ("AI_PORT", "65536"),
        ("AI_LOG_LEVEL", SENSITIVE_VALUE),
        ("AI_DATABASE_PATH", "   "),
        ("AI_DATABASE_PATH", "."),
        ("AI_DEFAULT_MODEL_BASE_URL", SENSITIVE_VALUE),
    ],
)
async def test_invalid_configuration_is_reported_without_values(monkeypatch, field, value):
    monkeypatch.setenv(field, value)
    monkeypatch.setenv("AI_DEFAULT_MODEL_API_KEY", SENSITIVE_VALUE)

    async with http_client() as client:
        response = await client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "configuration_error",
            "message": "Invalid server configuration.",
            "fields": [field],
        }
    }
    assert SENSITIVE_VALUE not in response.text
    assert "Traceback" not in response.text


async def test_health_does_not_create_database_or_business_data(monkeypatch, tmp_path):
    database_path = tmp_path / "not-created" / "business.sqlite3"
    monkeypatch.setenv("AI_DATABASE_PATH", str(database_path))

    async with http_client() as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert not database_path.parent.exists()


async def test_unknown_path_has_consistent_safe_error():
    async with http_client() as client:
        response = await client.get(f"/api/{SENSITIVE_VALUE}")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Resource not found."}
    }


async def test_method_not_allowed_preserves_allow_header():
    async with http_client() as client:
        response = await client.post("/api/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert "GET" in response.headers["allow"]


async def test_request_validation_does_not_echo_input():
    app = create_app()

    @app.get("/api/test-validation/{value}")
    async def test_validation_endpoint(value: int):
        return {"value": value}

    async with http_client(app) as client:
        response = await client.get(f"/api/test-validation/{SENSITIVE_VALUE}")

    assert response.status_code == 422
    assert response.json() == {
        "error": {"code": "validation_error", "message": "Invalid request."}
    }


async def test_unexpected_error_does_not_expose_exception_or_traceback(monkeypatch, caplog):
    monkeypatch.setenv("AI_LOG_LEVEL", "debug")
    app = create_app()

    @app.get("/api/test-error")
    async def test_error_endpoint():
        raise RuntimeError(SENSITIVE_VALUE)

    async with http_client(app, raise_app_exceptions=False) as client:
        response = await client.get("/api/test-error", headers={"Accept": "text/html"})

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Internal server error."}
    }
    assert SENSITIVE_VALUE not in response.text
    assert "Traceback" not in response.text
    assert SENSITIVE_VALUE not in caplog.text


def test_invalid_configuration_cli_exits_without_sensitive_output(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_PORT", SENSITIVE_VALUE)
    monkeypatch.setenv("AI_DEFAULT_MODEL_API_KEY", SENSITIVE_VALUE)
    result = subprocess.run(
        [sys.executable, "-m", "app"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 1
    assert "AI_PORT" in result.stderr
    assert SENSITIVE_VALUE not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr
