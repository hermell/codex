from unittest.mock import patch

from fastapi.testclient import TestClient

import fastapi_app


def test_index_page_renders_buttons_and_swagger_link():
    with patch("fastapi_app.runtime.start"), patch("fastapi_app.runtime.stop"):
        with TestClient(fastapi_app.app) as client:
            response = client.get("/")

    assert response.status_code == 200
    assert "Swagger 열기 (/docs)" in response.text
    assert "뉴스 수동 실행" in response.text


def test_health_endpoint_ok():
    with patch("fastapi_app.runtime.start"), patch("fastapi_app.runtime.stop"):
        with TestClient(fastapi_app.app) as client:
            response = client.get("/news/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_run_endpoint_calls_runtime_once():
    with (
        patch("fastapi_app.runtime.start"),
        patch("fastapi_app.runtime.stop"),
        patch("fastapi_app.runtime.run_once") as mock_run_once,
    ):
        with TestClient(fastapi_app.app) as client:
            response = client.post("/news/run")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    mock_run_once.assert_called_once()
